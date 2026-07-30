from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import ApplicationStatus, ApplicationType, NoticePeriod
from app.schemas.marketplace import ApplicationEventRead


class PriceLineRead(BaseModel):
    """Строка разбивки стоимости: за что и сколько."""

    kind: str
    label: str
    amount: Decimal


class ClientApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ApplicationType
    status: ApplicationStatus

    provider_id: UUID
    address_id: UUID
    provider_name: str
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
    # Разбивка «за что» и итог. Считаются тем же кодом, что и сумма счёта
    # (services/application_pricing), поэтому витрина не может разойтись
    # с тем, что клиент реально платит.
    price_lines: list[PriceLineRead] = Field(default_factory=list)
    price_total: Decimal = Decimal("0")
    events: list[ApplicationEventRead] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
