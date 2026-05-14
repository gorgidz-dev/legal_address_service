"""Generic-уведомления для пользователя.

`ApplicationEvent` остаётся источником уведомлений по заявкам, эту таблицу
используем для всего остального (новые сообщения в чате, системные алерты).
Frontend-инбокс агрегирует оба источника в один список.

Поля `link_type` / `link_id` нужны UI, чтобы понять куда вести при клике
("application" → открыть заявку, "chat" → открыть чат, ...).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserNotification(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user_notifications"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('chat_message', 'system')",
            name="user_notifications_kind_valid",
        ),
        CheckConstraint(
            "link_type IS NULL OR link_type IN ('application', 'chat')",
            name="user_notifications_link_type_valid",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link_type: Mapped[Optional[str]] = mapped_column(Text)
    link_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True))
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship()

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
