from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

CustomerStatus = Literal["active", "inactive"]
CustomerTier = Literal["std", "pro", "ent"]


class CustomerBase(BaseModel):
    partner_id: str = Field(..., min_length=1, max_length=100)
    partner_customer_id: str | None = Field(default=None, max_length=100)
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    status: CustomerStatus = "active"
    tier: CustomerTier = "std"
    tags: str | None = None
    note: str | None = None
    internal_note: str | None = None
    source_updated_at: datetime | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    partner_id: str | None = Field(default=None, min_length=1, max_length=100)
    partner_customer_id: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: CustomerStatus | None = None
    tier: CustomerTier | None = None
    tags: str | None = None
    note: str | None = None
    internal_note: str | None = None
    source_updated_at: datetime | None = None


class CustomerRead(CustomerBase):
    id: int
    source_updated_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CustomerList(BaseModel):
    items: list[CustomerRead]
    total: int
    page: int
    page_size: int


def current_utc_time() -> datetime:
    return datetime.now(timezone.utc)
