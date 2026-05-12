from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class Invitation(UUIDPKMixin, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
            name="role_valid",
        ),
        Index("ix_invitations_token_hash", "token_hash", unique=True),
        Index("ix_invitations_email", "email"),
        Index("ix_invitations_provider_id", "provider_id"),
        Index("ix_invitations_source_request_id", "source_request_id"),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))

    provider_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
    )
    source_request_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("provider_connection_requests.id", ondelete="SET NULL"),
    )
