from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings


async def store_upload(file: UploadFile) -> str:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "upload.csv").suffix.lower()
    stored_path = upload_dir / f"{uuid4()}{suffix}"

    with stored_path.open("wb") as destination:
        while chunk := await file.read(1024 * 1024):
            destination.write(chunk)

    return str(stored_path)
