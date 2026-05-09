from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
            name="role_valid",
        ),
        Index("ix_users_provider_id", "provider_id"),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
