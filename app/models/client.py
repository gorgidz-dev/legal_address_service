from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Client(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("length(inn) = 10", name="inn_length"),
        CheckConstraint("ogrn IS NULL OR length(ogrn) = 13", name="ogrn_length"),
        CheckConstraint("kpp IS NULL OR length(kpp) = 9", name="kpp_length"),
    )

    inn: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    kpp: Mapped[Optional[str]] = mapped_column(Text)
    ogrn: Mapped[Optional[str]] = mapped_column(Text)
    ogrn_date: Mapped[Optional[date]] = mapped_column(Date)
    okpo: Mapped[Optional[str]] = mapped_column(Text)
    okved_main_code: Mapped[Optional[str]] = mapped_column(Text)
    okved_main_name: Mapped[Optional[str]] = mapped_column(Text)

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_address: Mapped[Optional[str]] = mapped_column(Text)
    kladr_id: Mapped[Optional[str]] = mapped_column(Text)

    signatory_name: Mapped[Optional[str]] = mapped_column(Text)
    signatory_position: Mapped[Optional[str]] = mapped_column(Text)
    signatory_basis: Mapped[str] = mapped_column(Text, server_default="'Устава'", nullable=False)
    signatory_name_genitive: Mapped[Optional[str]] = mapped_column(Text)
    signatory_position_genitive: Mapped[Optional[str]] = mapped_column(Text)
    signatory_initials: Mapped[Optional[str]] = mapped_column(Text)

    bank_name: Mapped[Optional[str]] = mapped_column(Text)
    settlement_account: Mapped[Optional[str]] = mapped_column(Text)
    corr_account: Mapped[Optional[str]] = mapped_column(Text)
    bik: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)

    egrul_status: Mapped[Optional[str]] = mapped_column(Text)
    last_dadata_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
