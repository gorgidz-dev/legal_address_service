"""Календарь аренды: ближайшие сроки по действующим договорам.

Одна схема на оба кабинета. Отличается только `counterparty`: клиенту важно,
чей это адрес, собственнику — чья компания по нему сидит. Заводить две
почти одинаковые схемы ради одного поля смысла нет.

Классификация срока (`renewal_status`) переиспользует `renewal_state` из
реестра оператора: третья копия одной и той же арифметики разошлась бы с
первыми двумя.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.registry import RenewalStatus


class LeaseCalendarItem(BaseModel):
    application_id: UUID
    contract_id: UUID

    contract_number: str
    address_full: str
    room_number: Optional[str] = None
    #: Для клиента — собственник, для собственника — компания клиента.
    counterparty: str

    start_date: date
    end_date: date
    days_until_renewal: int
    renewal_status: RenewalStatus
    price_total: Decimal
