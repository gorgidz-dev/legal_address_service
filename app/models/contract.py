from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class Contract(UUIDPKMixin, Base):
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="end_after_start"),
        CheckConstraint("price_total > 0", name="price_positive"),
        Index("ix_contracts_contract_date", "contract_date"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="RESTRICT"),
        unique=True, nullable=False,
    )
    number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    contract_date: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_total_in_words: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
