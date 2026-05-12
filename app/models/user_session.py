from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class UserSession(UUIDPKMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_token_hash", "token_hash", unique=True),
        Index("ix_user_sessions_user_id", "user_id"),
        Index(
            "ix_user_sessions_refresh_token_hash",
            "refresh_token_hash",
            unique=True,
            postgresql_where=text("refresh_token_hash IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(Text)
    refresh_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    session_type: Mapped[Optional[str]] = mapped_column(Text)
    device_name: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(Text)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
