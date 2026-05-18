"""Отзыв клиента об адресе с рейтингом 1-5 и модерацией.

Бизнес-правила:
- Отзыв может оставить только клиент, у которого есть ЗАВЕРШЁННАЯ заявка
  (status=completed) по этому адресу — verified-purchase, защита от накрутки.
  Проверка делается в роутере при создании, здесь только хранение.
- Один отзыв на пару (адрес, клиент) — UniqueConstraint.
- Новый отзыв создаётся в статусе pending. Публично виден и попадает в
  средний рейтинг только после модерации (status=published).
- owner_reply — публичный ответ собственника на отзыв (один раз).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import ReviewStatus
from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.user import User


class AddressReview(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "address_reviews"
    __table_args__ = (
        UniqueConstraint(
            "address_id", "client_user_id", name="uq_address_reviews_pair"
        ),
        CheckConstraint(
            "rating BETWEEN 1 AND 5", name="address_reviews_rating_range"
        ),
        CheckConstraint("length(body) > 0", name="address_reviews_body_nonempty"),
    )

    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("addresses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Заявка, подтверждающая факт сделки (verified purchase).
    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )

    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=ReviewStatus.PENDING.value, index=True
    )

    # Модерация.
    moderated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    moderation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Публичный ответ собственника (один на отзыв).
    owner_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_reply_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    address: Mapped["Address"] = relationship()
    client: Mapped["User"] = relationship(foreign_keys=[client_user_id])
