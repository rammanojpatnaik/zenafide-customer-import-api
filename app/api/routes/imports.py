from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportError, ImportJob, User
from app.schemas import ImportErrorList, ImportJobRead, ImportJobSummary
from app.services.csv_import import create_import_job
from app.services.security import require_roles
from app.services.upload_storage import store_upload
from app.tasks import process_customer_import


router = APIRouter()


@router.post(
    "/customers",
    response_model=ImportJobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_customers(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported.",
        )

    stored_file_path = await store_upload(file)
    import_job = create_import_job(
        db,
        filename=file.filename,
        stored_file_path=stored_file_path,
        uploaded_by=current_user.id,
    )
    process_customer_import.delay(import_job.id)
    return build_import_summary(import_job)


@router.get("/{import_id}", response_model=ImportJobRead)
def get_import(
    import_id: int,
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    import_job = db.get(ImportJob, import_id)
    if not import_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found.",
        )
    return import_job


@router.get("/{import_id}/errors", response_model=ImportErrorList)
def list_import_errors(
    import_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_roles("admin", "operator")),
    db: Session = Depends(get_db),
):
    import_job = db.get(ImportJob, import_id)
    if not import_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Import job not found.",
        )

    total_statement = (
        select(func.count())
        .select_from(ImportError)
        .where(ImportError.import_job_id == import_id)
    )
    total = db.scalar(total_statement) or 0

    statement = (
        select(ImportError)
        .where(ImportError.import_job_id == import_id)
        .order_by(ImportError.row_number.asc(), ImportError.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    errors = db.scalars(statement).all()

    return {
        "items": errors,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def build_import_summary(import_job: ImportJob) -> dict[str, object]:
    return {
        "id": import_job.id,
        "filename": import_job.filename,
        "status": import_job.status,
        "total_rows": import_job.total_rows,
        "successful_rows": import_job.successful_rows,
        "failed_rows": import_job.failed_rows,
        "created_at": import_job.created_at,
        "completed_at": import_job.completed_at,
        "errors_url": f"/imports/{import_job.id}/errors",
    }
