from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportJob, RequestMetric


def record_request(db: Session, method: str, path: str, status_code: int) -> None:
    db.add(RequestMetric(method=method, path=path, status_code=status_code))
    db.commit()


def snapshot(db: Session) -> dict[str, object]:
    request_statement = (
        select(
            RequestMetric.method,
            RequestMetric.path,
            RequestMetric.status_code,
            func.count(RequestMetric.id),
        )
        .group_by(
            RequestMetric.method,
            RequestMetric.path,
            RequestMetric.status_code,
        )
        .order_by(
            RequestMetric.method,
            RequestMetric.path,
            RequestMetric.status_code,
        )
    )
    requests = [
        {
            "method": method,
            "path": path,
            "status_code": status_code,
            "count": count,
        }
        for method, path, status_code, count in db.execute(request_statement).all()
    ]

    import_status_statement = select(
        ImportJob.status,
        func.count(ImportJob.id),
    ).group_by(ImportJob.status)
    import_counts = dict(db.execute(import_status_statement).all())

    import_rows_statement = select(
        func.coalesce(func.sum(ImportJob.successful_rows), 0),
        func.coalesce(func.sum(ImportJob.failed_rows), 0),
    )
    successful_rows, failed_rows = db.execute(import_rows_statement).one()

    return {
        "requests": requests,
        "imports": {
            "by_status": import_counts,
            "rows": {
                "successful": successful_rows,
                "failed": failed_rows,
            },
        },
    }
