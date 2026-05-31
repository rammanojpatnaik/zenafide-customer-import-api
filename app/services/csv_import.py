import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models import Customer, ImportError, ImportJob

VALID_STATUSES = {"active", "inactive"}
VALID_TIERS = {"std", "pro", "ent"}
EXPECTED_COLUMN_COUNT = 10
logger = logging.getLogger(__name__)


class RowValidationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class MalformedCsvRow:
    row_number: int
    raw_row: str
    message: str


@dataclass
class ReconstructedCsv:
    text: str
    row_numbers: list[int]
    malformed_rows: list[MalformedCsvRow]


def create_import_job(
    db: Session,
    filename: str,
    stored_file_path: str,
    uploaded_by: int | None = None,
) -> ImportJob:
    import_job = ImportJob(
        filename=filename,
        stored_file_path=stored_file_path,
        status="pending",
        uploaded_by=uploaded_by,
    )
    db.add(import_job)
    db.commit()
    db.refresh(import_job)
    return import_job


def process_import_job(db: Session, import_job_id: int) -> ImportJob:
    import_job = db.get(ImportJob, import_job_id)
    if import_job is None:
        raise ValueError(f"Import job {import_job_id} does not exist.")

    prepare_import_job_for_attempt(db, import_job)
    logger.info(
        "customer_import_started",
        extra={"import_job_id": import_job.id, "import_filename": import_job.filename},
    )

    try:
        content = Path(import_job.stored_file_path).read_bytes()
        text = content.decode("utf-8-sig")
    except OSError:
        fail_import_job(
            db,
            import_job,
            error_code="stored_file_unavailable",
            message="Stored CSV file could not be read.",
        )
        raise
    except UnicodeDecodeError:
        fail_import_job(
            db,
            import_job,
            error_code="invalid_encoding",
            message="CSV file must be UTF-8 encoded.",
        )
        return import_job

    reconstructed_csv = reconstruct_logical_csv_rows(text, import_job.id)
    reader = csv.DictReader(StringIO(reconstructed_csv.text))
    if not reader.fieldnames:
        fail_import_job(
            db,
            import_job,
            error_code="missing_header",
            message="CSV file must include a header row.",
        )
        return import_job

    for malformed_row in reconstructed_csv.malformed_rows:
        import_job.total_rows += 1
        import_job.failed_rows += 1
        log_row_failure(
            import_job_id=import_job.id,
            row_number=malformed_row.row_number,
            error_code="invalid_column_count",
        )
        db.add(
            ImportError(
                import_job_id=import_job.id,
                row_number=malformed_row.row_number,
                raw_row=malformed_row.raw_row,
                error_code="invalid_column_count",
                message=malformed_row.message,
            )
        )

    for line_number, row in zip(reconstructed_csv.row_numbers, reader):
        import_job.total_rows += 1
        normalized_row = normalize_row(row)

        try:
            customer_data = validate_customer_row(normalized_row)
        except RowValidationError as exc:
            import_job.failed_rows += 1
            log_row_failure(
                import_job_id=import_job.id,
                row_number=line_number,
                error_code=exc.code,
            )
            db.add(
                ImportError(
                    import_job_id=import_job.id,
                    row_number=line_number,
                    raw_row=json.dumps(normalized_row),
                    error_code=exc.code,
                    message=exc.message,
                )
            )
            continue

        upsert_customer(db, customer_data)
        import_job.successful_rows += 1

    import_job.status = resolve_import_status(
        successful_rows=import_job.successful_rows,
        failed_rows=import_job.failed_rows,
    )
    import_job.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(import_job)
    finish_import_metrics_and_log(import_job)
    return import_job


def prepare_import_job_for_attempt(db: Session, import_job: ImportJob) -> None:
    db.execute(delete(ImportError).where(ImportError.import_job_id == import_job.id))
    import_job.status = "processing"
    import_job.total_rows = 0
    import_job.successful_rows = 0
    import_job.failed_rows = 0
    import_job.completed_at = None
    db.commit()
    db.refresh(import_job)


def fail_import_job(
    db: Session,
    import_job: ImportJob,
    error_code: str,
    message: str,
) -> None:
    import_job.status = "failed"
    import_job.failed_rows = 1
    import_job.completed_at = datetime.utcnow()
    db.add(
        ImportError(
            import_job_id=import_job.id,
            row_number=0,
            raw_row="",
            error_code=error_code,
            message=message,
        )
    )
    db.commit()
    db.refresh(import_job)
    finish_import_metrics_and_log(import_job)


def mark_import_job_retrying(db: Session, import_job_id: int) -> None:
    import_job = db.get(ImportJob, import_job_id)
    if import_job is None:
        return
    import_job.status = "retrying"
    db.commit()


def mark_import_job_failed_after_retries(db: Session, import_job_id: int) -> None:
    import_job = db.get(ImportJob, import_job_id)
    if import_job is None or import_job.status == "failed":
        return
    fail_import_job(
        db,
        import_job,
        error_code="worker_failed",
        message="Import failed after worker retries were exhausted.",
    )


def reconstruct_logical_csv_rows(text: str, import_job_id: int) -> ReconstructedCsv:
    physical_lines = text.splitlines()
    if not physical_lines:
        return ReconstructedCsv(text="", row_numbers=[], malformed_rows=[])

    header = physical_lines[0]
    logical_rows = []
    row_numbers = []
    malformed_rows = []
    index = 1

    while index < len(physical_lines):
        if not physical_lines[index].strip():
            index += 1
            continue

        start_line_number = index + 1
        buffered_line = physical_lines[index].strip()
        recovered_multiline = False

        while True:
            column_count = count_csv_columns(buffered_line)
            if column_count < EXPECTED_COLUMN_COUNT:
                index += 1
                if index >= len(physical_lines):
                    malformed_rows.append(
                        MalformedCsvRow(
                            row_number=start_line_number,
                            raw_row=buffered_line,
                            message=(
                                "CSV row ended before all 10 expected columns "
                                "could be reconstructed."
                            ),
                        )
                    )
                    break
                buffered_line = f"{buffered_line} {physical_lines[index].strip()}"
                recovered_multiline = True
                continue

            if column_count == EXPECTED_COLUMN_COUNT:
                logical_rows.append(buffered_line)
                row_numbers.append(start_line_number)
                if recovered_multiline:
                    logger.info(
                        "customer_import_multiline_recovered",
                        extra={
                            "import_job_id": import_job_id,
                            "row_number": start_line_number,
                        },
                    )
                index += 1
                break

            malformed_rows.append(
                MalformedCsvRow(
                    row_number=start_line_number,
                    raw_row=buffered_line,
                    message="CSV row contains more than the 10 expected columns.",
                )
            )
            index += 1
            break

    reconstructed_text = "\n".join([header, *logical_rows])
    return ReconstructedCsv(
        text=reconstructed_text,
        row_numbers=row_numbers,
        malformed_rows=malformed_rows,
    )


def count_csv_columns(buffered_line: str) -> int:
    try:
        return len(next(csv.reader([buffered_line])))
    except csv.Error:
        return EXPECTED_COLUMN_COUNT + 1


def log_row_failure(import_job_id: int, row_number: int, error_code: str) -> None:
    logger.warning(
        "customer_import_row_failed",
        extra={
            "import_job_id": import_job_id,
            "row_number": row_number,
            "error_code": error_code,
        },
    )


def finish_import_metrics_and_log(import_job: ImportJob) -> None:
    logger.info(
        "customer_import_completed",
        extra={
            "import_job_id": import_job.id,
            "import_filename": import_job.filename,
            "successful_rows": import_job.successful_rows,
            "failed_rows": import_job.failed_rows,
        },
    )


def normalize_row(row: dict[str, str | None]) -> dict[str, str]:
    return {
        (key or "").strip().lower(): (value or "").strip()
        for key, value in row.items()
    }


def validate_customer_row(row: dict[str, str]) -> dict[str, str | datetime | None]:
    partner_id = require_value(row, "p", "missing_partner_id", "Partner id is required.")
    email = require_value(row, "email", "missing_email", "Email is required.")
    name = require_value(row, "name", "missing_name", "Name is required.")
    status = require_value(row, "status", "missing_status", "Status is required.")
    upd = require_value(row, "upd", "missing_updated_at", "Update date is required.")

    try:
        normalized_email = validate_email(email, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise RowValidationError("invalid_email", str(exc)) from exc

    if status not in VALID_STATUSES:
        raise RowValidationError(
            "invalid_status",
            "Status must be one of: active, inactive.",
        )

    tier = row.get("tier") or "std"
    if tier not in VALID_TIERS:
        raise RowValidationError("invalid_tier", "Tier must be one of: std, pro, ent.")

    try:
        source_updated_at = datetime.strptime(upd, "%Y%m%d")
    except ValueError as exc:
        raise RowValidationError(
            "invalid_updated_at",
            "Update date must use YYYYMMDD format.",
        ) from exc

    return {
        "partner_id": partner_id,
        "partner_customer_id": row.get("cid") or None,
        "email": normalized_email,
        "name": name,
        "status": status,
        "tier": tier,
        "tags": row.get("tags") or None,
        "note": row.get("note") or None,
        "source_updated_at": source_updated_at,
    }


def require_value(
    row: dict[str, str],
    field: str,
    error_code: str,
    message: str,
) -> str:
    value = row.get(field)
    if not value:
        raise RowValidationError(error_code, message)
    return value


def upsert_customer(db: Session, customer_data: dict[str, str | datetime | None]) -> Customer:
    partner_id = str(customer_data["partner_id"])
    partner_customer_id = customer_data["partner_customer_id"]
    email = str(customer_data["email"])

    customer = find_existing_customer(
        db,
        partner_id=partner_id,
        partner_customer_id=str(partner_customer_id) if partner_customer_id else None,
        email=email,
    )

    if customer is None:
        customer = Customer(**customer_data)
        db.add(customer)
        db.flush()
        return customer

    incoming_updated_at = customer_data["source_updated_at"]
    if is_newer(incoming_updated_at, customer.source_updated_at):
        customer.partner_customer_id = customer_data["partner_customer_id"]
        customer.email = email
        customer.name = str(customer_data["name"])
        customer.status = str(customer_data["status"])
        customer.tier = str(customer_data["tier"])
        customer.tags = customer_data["tags"]
        customer.note = customer_data["note"]
        customer.source_updated_at = incoming_updated_at

    return customer


def find_existing_customer(
    db: Session,
    partner_id: str,
    partner_customer_id: str | None,
    email: str,
) -> Customer | None:
    if partner_customer_id:
        statement = select(Customer).where(
            Customer.partner_id == partner_id,
            or_(
                Customer.partner_customer_id == partner_customer_id,
                Customer.email == email,
            ),
        )
    else:
        statement = select(Customer).where(
            Customer.partner_id == partner_id,
            Customer.email == email,
        )
    return db.scalar(statement)


def is_newer(incoming: datetime, existing: datetime) -> bool:
    return incoming.replace(tzinfo=None) > existing.replace(tzinfo=None)


def resolve_import_status(successful_rows: int, failed_rows: int) -> str:
    if successful_rows > 0 and failed_rows > 0:
        return "partial_success"
    if failed_rows > 0:
        return "failed"
    return "completed"
