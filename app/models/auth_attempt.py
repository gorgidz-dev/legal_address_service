from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class AuthAttempt(UUIDPKMixin, Base):
    __tablename__ = "auth_attempts"
    __table_args__ = (
        CheckConstraint(
            "key_type IN ('email', 'ip')",
            name="ck_auth_attempts_key_type_valid",
        ),
        Index(
            "ix_auth_attempts_lookup",
            "scope",
            "key_type",
            "attempt_key",
            "created_at",
        ),
    )

    scope: Mapped[str] = mapped_column(Text, nullable=False)
    key_type: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_key: Mapped[str] = mapped_column(Text, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
