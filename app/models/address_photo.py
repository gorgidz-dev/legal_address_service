from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address


class AddressPhoto(UUIDPKMixin, TimestampMixin, Base):
    """Фотографии адреса. Загружает собственник, модерирует админ.

    Только одно фото на адрес может быть `is_main=True`, и только если
    статус модерации `approved` (см. uq partial-index в миграции 0006).
    """

    __tablename__ = "address_photos"
    __table_args__ = (
        CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected')",
            name="moderation_status_valid",
        ),
        CheckConstraint("size_bytes > 0", name="size_bytes_positive"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        Index("ix_address_photos_address_id", "address_id", "moderation_status"),
        Index("ix_address_photos_moderation_status", "moderation_status", "created_at"),
    )

    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("addresses.id", ondelete="CASCADE"),
        nullable=False,
    )

    storage_backend: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)

    moderation_status: Mapped[str] = mapped_column(
        Text,
        server_default="'pending'",
        nullable=False,
    )
    moderation_comment: Mapped[Optional[str]] = mapped_column(Text)
    moderated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    is_main: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, server_default="0", nullable=False)

    uploaded_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    address: Mapped["Address"] = relationship()
