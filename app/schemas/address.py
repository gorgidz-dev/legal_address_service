from __future__ import annotations

"""Pydantic-схемы для помещения, привязанного к собственнику."""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import ADDRESS_AMENITY_VALUES
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

    amenities: list[str] = Field(
        default_factory=list,
        description="Характеристики помещения: metro, parking, security, concierge, elevator",
    )

    @field_validator("amenities")
    @classmethod
    def _known_amenities(cls, value: list[str]) -> list[str]:
        """Только значения из справочника и без повторов.

        Порядок сохраняем — собственник отмечает то, что считает важным, и в
        карточке иконки идут в этом же порядке.
        """
        unknown = sorted(set(value) - set(ADDRESS_AMENITY_VALUES))
        if unknown:
            raise ValueError(f"Неизвестные характеристики: {', '.join(unknown)}")
        seen: set[str] = set()
        return [x for x in value if not (x in seen or seen.add(x))]


class AddressCreate(AddressBase):
    provider_id: UUID


class AddressRead(AddressBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    is_available: bool
    publication_status: str
    published_at: Optional[datetime] = None
    moderation_comment: Optional[str] = None
    moderated_by: Optional[UUID] = None
    moderated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AddressModerationReject(BaseModel):
    moderation_comment: str = Field(min_length=2, max_length=2000)
