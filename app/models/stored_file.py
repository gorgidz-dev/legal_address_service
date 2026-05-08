from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class StoredFile(UUIDPKMixin, Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        Index("ix_stored_files_client_id", "client_id", "created_at"),
        Index("ix_stored_files_application_id", "application_id", "created_at"),
        Index("ix_stored_files_kind", "kind"),
    )

    client_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("clients.id"))
    application_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("applications.id"))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_backend: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
