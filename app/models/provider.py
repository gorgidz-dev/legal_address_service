from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address


class Provider(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("inn IS NULL OR length(inn) IN (10, 12)", name="inn_length"),
        CheckConstraint("ogrn IS NULL OR length(ogrn) IN (13, 15)", name="ogrn_length"),
        CheckConstraint("bik IS NULL OR length(bik) = 9", name="bik_length"),
        Index("ix_providers_is_active", "is_active"),
    )

    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[str] = mapped_column(Text, nullable=False)

    inn: Mapped[Optional[str]] = mapped_column(Text)
    kpp: Mapped[Optional[str]] = mapped_column(Text)
    ogrn: Mapped[Optional[str]] = mapped_column(Text)
    okpo: Mapped[Optional[str]] = mapped_column(Text)
    legal_address: Mapped[Optional[str]] = mapped_column(Text)

    signatory_name: Mapped[Optional[str]] = mapped_column(Text)
    signatory_position: Mapped[Optional[str]] = mapped_column(Text)
    signatory_basis: Mapped[Optional[str]] = mapped_column(Text)
    signatory_name_genitive: Mapped[Optional[str]] = mapped_column(Text)
    signatory_position_genitive: Mapped[Optional[str]] = mapped_column(Text)
    signatory_initials: Mapped[Optional[str]] = mapped_column(Text)

    bank_name: Mapped[Optional[str]] = mapped_column(Text)
    settlement_account: Mapped[Optional[str]] = mapped_column(Text)
    corr_account: Mapped[Optional[str]] = mapped_column(Text)
    bik: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    addresses: Mapped[list["Address"]] = relationship(back_populates="provider")
