from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import AddressPublicationStatus, ApplicationStatus, ApplicationType, NoticePeriod
from app.schemas.marketplace import ApplicationEventRead
from app.schemas.provider import ProviderRead


class OwnerAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    full_address: str
    room_number: Optional[str]
    cadastral_number: str
    price_6m: Decimal
    price_11m: Decimal
    correspondence_price: Optional[Decimal]
    fns_number: Optional[int]
    fns_city: Optional[str]
    is_available: bool
    publication_status: AddressPublicationStatus
    created_at: datetime
    updated_at: datetime


class OwnerApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ApplicationType
    status: ApplicationStatus

    provider_id: UUID
    address_id: UUID
    full_address: str
    room_number: Optional[str]

    client_id: Optional[UUID] = None
    planned_client_name: Optional[str] = None
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    term_months: Optional[int] = None
    notice_period: Optional[NoticePeriod] = None
    has_correspondence_service: bool
    contract_city: Optional[str] = None

    fns_number: Optional[int] = None
    fns_city: Optional[str] = None
    expires_at: Optional[date] = None
    parent_application_id: Optional[UUID] = None

    selected_price: Decimal
    correspondence_price: Optional[Decimal]
    available_actions: list[str] = Field(default_factory=list)
    events: list[ApplicationEventRead] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime


class OwnerDashboardRead(BaseModel):
    provider: ProviderRead
    addresses: list[OwnerAddressRead] = Field(default_factory=list)
    applications: list[OwnerApplicationRead] = Field(default_factory=list)
