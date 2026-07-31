"""Карточка правоустанавливающего документа адреса."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from app.enums import AddressDocumentKind

#: `none` — бессрочный документ, а не «неизвестно».
ExpiryState = Literal["none", "expired", "soon", "valid"]


class AddressDocumentRead(BaseModel):
    id: UUID
    address_id: UUID
    kind: AddressDocumentKind
    kind_label: str
    title: str

    original_filename: str
    size_bytes: int
    download_url: str

    issued_on: Optional[date] = None
    expires_at: Optional[date] = None
    expiry_state: ExpiryState
    #: Отрицательное — документ уже просрочен. None у бессрочных.
    days_until_expiry: Optional[int] = None

    notes: Optional[str] = None
    created_at: datetime
