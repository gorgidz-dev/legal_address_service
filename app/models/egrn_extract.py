from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address


class EgrnExtract(UUIDPKMixin, Base):
    __tablename__ = "egrn_extracts"
    __table_args__ = (
        CheckConstraint("expires_at > issue_date", name="expiry_after_issue"),
        # Только одна актуальная выписка на адрес — partial unique index.
        Index(
            "uniq_current_egrn_per_address",
            "address_id",
            unique=True,
            postgresql_where="is_current = true",
        ),
        Index("ix_egrn_extracts_address_id", "address_id", "issue_date"),
    )

    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("addresses.id", ondelete="RESTRICT"),
        nullable=False,
    )

    pdf_file_url: Mapped[str] = mapped_column(Text, nullable=False)
    signature_file_url: Mapped[Optional[str]] = mapped_column(Text)
    extract_number: Mapped[Optional[str]] = mapped_column(Text)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[date] = mapped_column(Date, nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(Text, nullable=False)

    is_current: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    replaced_by_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("egrn_extracts.id"),
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"),
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    address: Mapped["Address"] = relationship(back_populates="egrn_extracts")
