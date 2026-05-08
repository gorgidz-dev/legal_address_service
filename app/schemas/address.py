from __future__ import annotations

"""Pydantic-схемы для помещения, привязанного к собственнику."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.validators import CadastralNumber


class AddressBase(BaseModel):
    full_address: str = Field(examples=["123456, г. Москва, ул. Тверская, д. 1, помещение № 5"])
    room_number: Optional[str] = Field(default=None, examples=["офис 12"])
    cadastral_number: CadastralNumber = Field(examples=["77:01:0001001:1234"])

    ownership_doc: str = Field(
        examples=["Выписка из ЕГРН от 12.04.2026 № КУВИ-001/2026-12345"],
        description="Полный текст ссылки на документ-основание права (для приложения и журналов)",
    )
    ownership_doc_short: str = Field(
        examples=["Выписки из ЕГРН"],
        description="Короткая форма для перечня приложений в гарантийном письме",
    )
    ownership_doc_pages: int = Field(default=1, ge=1, le=999)

    price_6m: Decimal = Field(gt=0, description="Стоимость пакета на 6 месяцев, руб.")
    price_11m: Decimal = Field(gt=0, description="Стоимость пакета на 11 месяцев, руб.")
    correspondence_price: Optional[Decimal] = Field(
        default=None, ge=0, description="Цена опции «приём корреспонденции»"
    )

    fns_number: Optional[int] = Field(default=None, ge=1, le=9999, examples=[46])
    fns_city: Optional[str] = Field(default=None, examples=["Москве"])

    notes: Optional[str] = None


class AddressCreate(AddressBase):
    provider_id: UUID


class AddressRead(AddressBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    is_available: bool
    created_at: datetime
    updated_at: datetime
