from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.provider import Provider
    from app.models.egrn_extract import EgrnExtract


class Address(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "addresses"
    __table_args__ = (
        CheckConstraint("price_6m > 0 AND price_11m > 0", name="prices_positive"),
        CheckConstraint("ownership_doc_pages > 0", name="pages_positive"),
        CheckConstraint(
            "publication_status IN ('draft', 'moderation', 'published', 'rejected', 'archived')",
            name="publication_status_valid",
        ),
        Index("ix_addresses_provider_id", "provider_id", "is_available"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="RESTRICT"),
        nullable=False,
    )

    full_address: Mapped[str] = mapped_column(Text, nullable=False)
    room_number: Mapped[Optional[str]] = mapped_column(Text)
    cadastral_number: Mapped[str] = mapped_column(Text, nullable=False)

    ownership_doc: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_doc_short: Mapped[str] = mapped_column(Text, nullable=False)
    ownership_doc_pages: Mapped[int] = mapped_column(SmallInteger, server_default="1", nullable=False)

    price_6m: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_11m: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    correspondence_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))

    fns_number: Mapped[Optional[int]] = mapped_column(SmallInteger)
    fns_city: Mapped[Optional[str]] = mapped_column(Text)

    is_available: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    publication_status: Mapped[str] = mapped_column(
        Text,
        server_default="'draft'",
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    moderation_comment: Mapped[Optional[str]] = mapped_column(Text)
    moderated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    provider: Mapped["Provider"] = relationship(back_populates="addresses")
    egrn_extracts: Mapped[list["EgrnExtract"]] = relationship(back_populates="address")
