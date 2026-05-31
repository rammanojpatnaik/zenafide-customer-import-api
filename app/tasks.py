import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.csv_import import (
    mark_import_job_failed_after_retries,
    mark_import_job_retrying,
    process_import_job,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
)
def process_customer_import(self, import_job_id: int) -> None:
    try:
        with SessionLocal() as db:
            process_import_job(db, import_job_id)
    except Exception as exc:
        logger.exception(
            "customer_import_task_failed",
            extra={
                "import_job_id": import_job_id,
                "retry_number": self.request.retries,
            },
        )
        if self.request.retries >= self.max_retries:
            with SessionLocal() as db:
                mark_import_job_failed_after_retries(db, import_job_id)
            raise

        with SessionLocal() as db:
            mark_import_job_retrying(db, import_job_id)
        raise self.retry(exc=exc, countdown=2**self.request.retries)
