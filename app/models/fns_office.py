"""Справочник налоговых инспекций (ИФНС).

Иерархия каталога Регион → Город → ИФНС строится из этого справочника:
адрес ссылается на запись через addresses.fns_office_id, а регион и город —
атрибуты самой инспекции (ИФНС всегда принадлежит одному городу).

Заполняется из DaData address-suggest (поле data.tax_office) при создании
адреса, плюс стартовый сид по Москве (scripts/seed_fns_offices.py).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class FnsOffice(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "fns_offices"
    __table_args__ = (
        Index("ix_fns_offices_region_city", "region", "city"),
    )

    # Федеральный код ИФНС (DaData tax_office), например "7746". Уникален.
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Человекочитаемое название, напр. "ИФНС России № 46 по г. Москве".
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Локальный номер инспекции (то, что показываем как «ИФНС № N»).
    short_number: Mapped[Optional[int]] = mapped_column()
    region: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(Text, nullable=False)
