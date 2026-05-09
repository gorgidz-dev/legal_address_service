from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.enums import ApplicationEventKind, NotificationAudience, OwnerConnectionRequestStatus


class ProviderConnectionRequestCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=300)
    contact_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr
    contact_phone: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=120)
    address_count: Optional[int] = Field(default=None, ge=0, le=10_000)
    comment: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("contact_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        local, _, domain = value.partition("@")
        return f"{local}@{domain.lower()}"


class ProviderConnectionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    contact_name: str
    contact_email: EmailStr
    contact_phone: Optional[str]
    city: Optional[str]
    address_count: Optional[int]
    comment: Optional[str]
    status: OwnerConnectionRequestStatus
    admin_comment: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ApplicationEventCreate(BaseModel):
    application_id: UUID
    kind: ApplicationEventKind
    audience: NotificationAudience
    title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=2, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    kind: ApplicationEventKind
    audience: NotificationAudience
    title: str
    message: str
    payload: dict[str, Any]
    is_read: bool
    created_by: Optional[UUID]
    created_at: datetime
    read_at: Optional[datetime]


class PublicAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    provider_name: str
    full_address: str
    room_number: Optional[str]
    price_6m: Decimal
    price_11m: Decimal
    selected_price: Decimal
    correspondence_price: Optional[Decimal]
    fns_number: Optional[int]
    fns_city: Optional[str]
    is_available: bool
    publication_status: str
    created_at: datetime
    updated_at: datetime
