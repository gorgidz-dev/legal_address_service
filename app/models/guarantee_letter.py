from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class GuaranteeLetter(UUIDPKMixin, Base):
    __tablename__ = "guarantee_letters"
    __table_args__ = (
        CheckConstraint("variant IN ('initial', 'full')", name="variant_valid"),
        Index("ix_guarantee_letters_application_id", "application_id"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="RESTRICT"),
        nullable=False,
    )
    variant: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    letter_date: Mapped[date] = mapped_column(Date, nullable=False)
    egrn_extract_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("egrn_extracts.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
