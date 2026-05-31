import pytest
from sqlalchemy import func, select

from app.models import Customer, ImportError, ImportJob
from app.services.csv_import import create_import_job, process_import_job
from app.tasks import process_customer_import


def test_upload_returns_pending_job_before_worker_processes(client, monkeypatch):
    queued_job_ids = []
    monkeypatch.setattr(
        "app.api.routes.imports.process_customer_import.delay",
        lambda import_job_id: queued_job_ids.append(import_job_id),
    )
    csv_text = """p,row,cid,email,name,status,tier,upd,tags,note
p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email
"""

    response = client.post(
        "/imports/customers",
        files={"file": ("customers.csv", csv_text, "text/csv")},
    )

    assert response.status_code == 202
    summary = response.json()
    assert summary["status"] == "pending"
    assert summary["total_rows"] == 0
    assert queued_job_ids == [summary["id"]]


def test_worker_retry_resets_errors_and_counters(db_session, tmp_path):
    stored_file = tmp_path / "retry.csv"
    stored_file.write_text(
        "p,row,cid,email,name,status,tier,upd,tags,note\n"
        "p1,001,C1001,ada@x.io,Ada Lovelace,active,ent,20260420,vip,email\n"
        "p1,002,C1002,bad-email,Hedy Lamarr,active,pro,20260420,wireless,bad-email\n"
    )
    import_job = create_import_job(
        db_session,
        filename="retry.csv",
        stored_file_path=str(stored_file),
    )

    first_attempt = process_import_job(db_session, import_job.id)
    second_attempt = process_import_job(db_session, import_job.id)

    assert first_attempt.status == "partial_success"
    assert second_attempt.status == "partial_success"
    assert second_attempt.total_rows == 2
    assert second_attempt.successful_rows == 1
    assert second_attempt.failed_rows == 1
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ImportError)
            .where(ImportError.import_job_id == import_job.id)
        )
        == 1
    )


def test_worker_marks_job_failed_after_retries(client, db_session, monkeypatch, tmp_path):
    stored_file = tmp_path / "retry.csv"
    stored_file.write_text("p,row,cid,email,name,status,tier,upd,tags,note\n")
    import_job = create_import_job(
        db_session,
        filename="retry.csv",
        stored_file_path=str(stored_file),
    )
    monkeypatch.setattr(
        "app.tasks.process_import_job",
        lambda db, import_job_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    process_customer_import.push_request(retries=3)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            process_customer_import.run(import_job.id)
    finally:
        process_customer_import.pop_request()

    persisted_job = db_session.get(ImportJob, import_job.id)
    assert persisted_job is not None
    assert persisted_job.status == "failed"
    error = db_session.scalar(
        select(ImportError).where(ImportError.import_job_id == import_job.id)
    )
    assert error is not None
    assert error.error_code == "worker_failed"
