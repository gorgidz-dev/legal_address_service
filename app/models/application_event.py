from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class ApplicationEvent(UUIDPKMixin, Base):
    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('created', 'status_changed', 'comment_added', 'document_uploaded', "
            "'document_approved', 'correction_requested', 'dispute_opened', 'cancelled')",
            name="kind_valid",
        ),
        CheckConstraint("audience IN ('client', 'owner', 'admin')", name="audience_valid"),
        Index("ix_application_events_application_created", "application_id", "created_at"),
        Index("ix_application_events_audience_read", "audience", "is_read", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
