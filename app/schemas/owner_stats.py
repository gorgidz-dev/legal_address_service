"""Отдача по адресу в кабинете собственника."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class OwnerAddressStats(BaseModel):
    address_id: UUID
    #: Все заявки по адресу, включая неоплаченные и отменённые.
    applications_total: int
    #: Заявки, по которым платёж подтверждён.
    deals_paid: int
    #: Сумма подтверждённых платежей, в рублях.
    revenue: Decimal
    last_paid_at: Optional[datetime] = None
