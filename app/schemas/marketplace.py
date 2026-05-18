from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contacts import ContactName, Email, OptionalPhone
from app.enums import (
    ApplicationEventKind,
    ApplicationType,
    NoticePeriod,
    NotificationAudience,
    OwnerConnectionRequestStatus,
    PaymentPayerType,
)
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
    invitation_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class ProviderConnectionRequestStatusUpdate(BaseModel):
    """Перевод заявки в статус reviewing/rejected. Approve — отдельный эндпоинт."""

    status: Literal[OwnerConnectionRequestStatus.REVIEWING, OwnerConnectionRequestStatus.REJECTED]
    admin_comment: Optional[str] = Field(default=None, max_length=2000)


class ProviderConnectionRequestApprove(BaseModel):
    """Превращает заявку в провайдера + приглашение на роль owner."""

    code: str = Field(min_length=1, max_length=50, examples=["msk-tverskaya-1"])
    short_name: str = Field(min_length=1, max_length=300, examples=["ИП Иванов И. И."])
    full_name: str = Field(min_length=1, max_length=500, examples=["ИП Иванов Иван Иванович"])
    admin_comment: Optional[str] = Field(default=None, max_length=2000)


class ProviderConnectionRequestApproveResult(BaseModel):
    request: ProviderConnectionRequestRead
    provider_id: UUID
    invitation_id: UUID
    invitation_token: str
    invitation_path: str
    invitation_expires_at: datetime


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
    # Для смены адреса клиент выбирает способ оплаты: СБП от физлица или счёт на ЮЛ.
    # При INITIAL_REGISTRATION ЮЛ ещё не существует, поэтому payer_type всегда individual.
    payer_type: Literal[PaymentPayerType.INDIVIDUAL, PaymentPayerType.JURIDICAL] = (
        PaymentPayerType.INDIVIDUAL
    )


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


class PublicAddressServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    price: Decimal
    is_active: bool


class PublicAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    provider_name: str
    full_address: str
    room_number: Optional[str]
    description: Optional[str] = None
    price_6m: Decimal
    price_11m: Decimal
    selected_price: Decimal
    correspondence_price: Optional[Decimal]
    fns_number: Optional[int]
    fns_city: Optional[str]
    # Координаты для карты. None — адрес не геокодирован.
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_available: bool
    publication_status: str
    created_at: datetime
    updated_at: datetime
    photos: list[AddressPhotoRead] = Field(default_factory=list)
    main_photo_url: Optional[str] = None
    services: list[PublicAddressServiceRead] = Field(default_factory=list)
    # Агрегаты рейтинга: средний балл (None если отзывов нет) и кол-во
    # опубликованных отзывов.
    rating_avg: Optional[float] = None
    rating_count: int = 0


# ============================== Reviews ==============================


class AddressReviewCreate(BaseModel):
    """Создание отзыва клиентом. application_id подбирается на бэке."""

    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=10, max_length=2000)


class PublicReviewRead(BaseModel):
    """Опубликованный отзыв для витрины (без PII клиента)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rating: int
    body: str
    author_name: str
    created_at: datetime
    owner_reply: Optional[str] = None
    owner_reply_at: Optional[datetime] = None


class MyReviewRead(BaseModel):
    """Собственный отзыв клиента — со статусом модерации (для edit/delete UI)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    rating: int
    body: str
    status: str
    moderation_note: Optional[str] = None
    owner_reply: Optional[str] = None
    created_at: datetime


class ModerationReviewRead(BaseModel):
    """Отзыв в админ-очереди модерации — со всеми служебными полями."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    address_full: str
    client_email: str
    rating: int
    body: str
    status: str
    moderation_note: Optional[str] = None
    moderated_at: Optional[datetime] = None
    owner_reply: Optional[str] = None
    created_at: datetime


class ReviewModerationAction(BaseModel):
    """Действие модератора: publish | reject (+ опц. заметка)."""

    action: Literal["publish", "reject"]
    note: Optional[str] = Field(default=None, max_length=500)


class OwnerReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
