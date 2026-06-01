"""Upload storage backend.

Supports two backends selected by the STORAGE_BACKEND env var:

- ``local`` (default): writes files to the local filesystem at ``UPLOAD_DIR``.
  Works for single-host Docker Compose deployments where the API and worker
  share a volume.

- ``s3``: uploads files to an S3-compatible bucket.  Required for multi-service
  cloud deployments (Railway, Fly.io, etc.) where the API and worker run on
  separate machines.  Configure with:

      STORAGE_BACKEND=s3
      S3_BUCKET=<bucket-name>
      S3_REGION=<region>          # defaults to us-east-1
      AWS_ACCESS_KEY_ID=<key>
      AWS_SECRET_ACCESS_KEY=<secret>
      S3_ENDPOINT_URL=<url>       # optional, for non-AWS providers (e.g. R2, MinIO)
"""

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)


async def store_upload(file: UploadFile) -> str:
    """Persist an uploaded file and return a storage key/path for later retrieval."""
    if settings.storage_backend == "s3":
        return await _store_s3(file)
    return await _store_local(file)


def read_upload(stored_path: str) -> bytes:
    """Read a previously stored upload by its storage key/path."""
    if settings.storage_backend == "s3":
        return _read_s3(stored_path)
    return Path(stored_path).read_bytes()


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------

async def _store_local(file: UploadFile) -> str:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.csv").suffix.lower()
    stored_path = upload_dir / f"{uuid4()}{suffix}"

    with stored_path.open("wb") as destination:
        while chunk := await file.read(1024 * 1024):
            destination.write(chunk)

    logger.debug("upload_stored_local", extra={"path": str(stored_path)})
    return str(stored_path)


# ---------------------------------------------------------------------------
# S3 backend
# ---------------------------------------------------------------------------

def _s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3 storage. "
            "Install it with: pip install boto3"
        ) from exc

    kwargs: dict = {
        "region_name": settings.s3_region,
    }
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url

    return boto3.client("s3", **kwargs)


async def _store_s3(file: UploadFile) -> str:
    if not settings.s3_bucket:
        raise RuntimeError(
            "S3_BUCKET must be set when STORAGE_BACKEND=s3"
        )

    suffix = Path(file.filename or "upload.csv").suffix.lower()
    key = f"uploads/{uuid4()}{suffix}"

    content = await file.read()
    _s3_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType="text/csv",
    )
    logger.debug("upload_stored_s3", extra={"bucket": settings.s3_bucket, "key": key})
    return key


def _read_s3(key: str) -> bytes:
    if not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET must be set when STORAGE_BACKEND=s3")

    response = _s3_client().get_object(Bucket=settings.s3_bucket, Key=key)
    return response["Body"].read()
