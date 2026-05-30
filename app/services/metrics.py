from collections import Counter
from threading import Lock

_lock = Lock()
_request_counts: Counter[tuple[str, str, int]] = Counter()
_import_counts: Counter[str] = Counter()
_import_rows: Counter[str] = Counter()


def record_request(method: str, path: str, status_code: int) -> None:
    with _lock:
        _request_counts[(method, path, status_code)] += 1


def record_import(status: str, successful_rows: int, failed_rows: int) -> None:
    with _lock:
        _import_counts[status] += 1
        _import_rows["successful"] += successful_rows
        _import_rows["failed"] += failed_rows


def snapshot() -> dict[str, object]:
    with _lock:
        requests = [
            {
                "method": method,
                "path": path,
                "status_code": status_code,
                "count": count,
            }
            for (method, path, status_code), count in sorted(_request_counts.items())
        ]
        return {
            "requests": requests,
            "imports": {
                "by_status": dict(_import_counts),
                "rows": dict(_import_rows),
            },
        }
