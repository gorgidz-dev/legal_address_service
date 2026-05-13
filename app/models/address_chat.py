"""Чат между клиентом и собственником адреса.

Один чат — на пару (адрес, клиент). Сообщения хранятся отдельной таблицей.
Доступ к чату требует регистрации/входа; собственник адреса видит все чаты
по своим адресам, клиент — только свои.

TODO(moderation): авто-модерация сообщений (без оскорблений и контактов)
будет добавлена позже. Сейчас тело сообщения хранится как есть.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.user import User


class AddressChat(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "address_chats"
    __table_args__ = (
        UniqueConstraint("address_id", "client_user_id", name="uq_address_chats_pair"),
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
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    address: Mapped["Address"] = relationship()
    client: Mapped["User"] = relationship()
    messages: Mapped[list["AddressChatMessage"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="AddressChatMessage.created_at",
    )


class AddressChatMessage(UUIDPKMixin, Base):
    __tablename__ = "address_chat_messages"
    __table_args__ = (
        CheckConstraint("length(body) > 0", name="address_chat_messages_body_nonempty"),
    )

    chat_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("address_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped["AddressChat"] = relationship(back_populates="messages")
