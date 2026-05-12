from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contacts import ContactName, Email, OptionalPhone
from app.enums import ApplicationEventKind, ApplicationType, NoticePeriod, NotificationAudience, OwnerConnectionRequestStatus
from app.schemas.address_photo import AddressPhotoRead
from app.schemas.application import ApplicationRead
from app.schemas.auth import CurrentUserRead
from app.validators import INNLegal


class ProviderConnectionRequestCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=300)
    contact_name: ContactName
    contact_email: Email
    contact_phone: OptionalPhone = None
    city: Optional[str] = Field(default=None, max_length=120)
    address_count: Optional[int] = Field(default=None, ge=0, le=10_000)
    comment: Optional[str] = Field(default=None, max_length=2000)


class ProviderConnectionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    contact_name: str
    contact_email: str
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


class _PublicClientApplicationCreateBase(BaseModel):
    address_id: UUID
    contact_name: ContactName
    contact_email: Email
    contact_phone: OptionalPhone = None
    password: str = Field(min_length=8, max_length=200)
    term_months: Literal[6, 11] = 11
    has_correspondence_service: bool = False
    contract_city: Optional[str] = Field(default=None, max_length=120)


class PublicClientApplicationCreateInitial(_PublicClientApplicationCreateBase):
    type: Literal[ApplicationType.INITIAL_REGISTRATION] = ApplicationType.INITIAL_REGISTRATION
    planned_client_name: str = Field(min_length=1, max_length=200)


class PublicClientApplicationCreateAddressChange(_PublicClientApplicationCreateBase):
    type: Literal[ApplicationType.ADDRESS_CHANGE] = ApplicationType.ADDRESS_CHANGE
    client_inn: INNLegal
    notice_period: NoticePeriod = NoticePeriod.ONE_MONTH


PublicClientApplicationCreate = Annotated[
    Union[PublicClientApplicationCreateInitial, PublicClientApplicationCreateAddressChange],
    Field(discriminator="type"),
]


class PublicClientApplicationResult(BaseModel):
    user: CurrentUserRead
    application: ApplicationRead


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
    photos: list[AddressPhotoRead] = Field(default_factory=list)
    main_photo_url: Optional[str] = None
