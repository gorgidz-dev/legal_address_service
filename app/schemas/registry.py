from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


RenewalStatus = Literal["overdue", "due_soon", "active"]


def renewal_state(renewal_date: date, *, today: date | None = None) -> RenewalStatus:
    current = today or date.today()
    days_left = (renewal_date - current).days
    if days_left < 0:
        return "overdue"
    if days_left <= 30:
        return "due_soon"
    return "active"


class ActiveClientRegistryItem(BaseModel):
    application_id: UUID
    contract_id: UUID
    client_id: UUID

    company_name: str
    client_inn: str

    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]

    provider_name: str
    address_full: str

    contract_number: str
    contract_date: date
    start_date: date
    end_date: date
    renewal_date: date
    term_months: int
    days_until_renewal: int
    price_total: Decimal
    renewal_status: RenewalStatus
