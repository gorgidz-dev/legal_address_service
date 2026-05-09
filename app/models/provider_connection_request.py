from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProviderConnectionRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "provider_connection_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'reviewing', 'invited', 'rejected')",
            name="status_valid",
        ),
        CheckConstraint("address_count IS NULL OR address_count >= 0", name="address_count_non_negative"),
        Index("ix_provider_connection_requests_status_created", "status", "created_at"),
        Index("ix_provider_connection_requests_contact_email", "contact_email"),
    )

    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text)
    address_count: Mapped[Optional[int]] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="'new'", nullable=False)
    admin_comment: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
