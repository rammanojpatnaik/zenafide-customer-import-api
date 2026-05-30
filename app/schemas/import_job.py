from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportJobRead(BaseModel):
    id: int
    filename: str
    status: str
    total_rows: int
    successful_rows: int
    failed_rows: int
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ImportJobSummary(ImportJobRead):
    errors_url: str


class ImportErrorRead(BaseModel):
    id: int
    import_job_id: int
    row_number: int
    raw_row: str
    error_code: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportErrorList(BaseModel):
    items: list[ImportErrorRead]
    total: int
    page: int
    page_size: int
