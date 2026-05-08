from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class DocumentTemplate(UUIDPKMixin, Base):
    __tablename__ = "document_templates"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('contract', 'guarantee_initial', 'guarantee_full')",
            name="kind_valid",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        UniqueConstraint("kind", "version", name="uq_kind_version"),
        # Только одна активная версия каждого вида.
        Index(
            "uniq_active_template_per_kind",
            "kind", unique=True,
            postgresql_where="is_active = true",
        ),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"),
    )
