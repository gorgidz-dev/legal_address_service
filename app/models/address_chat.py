"""Переписка по адресу: клиент, собственник и площадка в одной ветке.

Одна ветка — на пару (адрес, клиент). Заявок по этой паре может быть несколько
(первичка, потом продление), но разговор один и тот же, поэтому ветка ключена
на адрес и клиента, а не на заявку: иначе при продлении вся история переписки
осталась бы в старой заявке.

Участников трое. Клиент и собственники адреса — очевидные, площадка (admin /
manager / lawyer) — полноправный третий: она и читает, и пишет, и получает
уведомления. Правила участия живут в services/chat_threads.py, чтобы новая
ручка не завела свою копию проверки.

TODO(moderation): авто-модерация сообщений (без оскорблений и контактов)
будет добавлена позже. Сейчас тело сообщения хранится как есть.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address
    from app.models.stored_file import StoredFile
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
    """Сообщение ветки.

    Пустое тело допустимо, но только вместе с вложением — сообщение «вот
    договор» без единого слова это нормально. Проверку «текст или файл» держит
    сервис: БД не видит дочернюю таблицу вложений и такой инвариант выразить
    не может, а денормализованный счётчик рано или поздно разъедется с фактом.
    """

    __tablename__ = "address_chat_messages"

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
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    chat: Mapped["AddressChat"] = relationship(back_populates="messages")
    attachments: Mapped[list["ChatMessageAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatMessageAttachment.created_at",
    )


class ChatMessageAttachment(UUIDPKMixin, Base):
    """Файл, прикреплённый к сообщению.

    Сам файл лежит в stored_files (то же хранилище, что у документов заявки),
    здесь только привязка к сообщению. Так вложение чата и документ заявки
    хранятся одинаково — и одинаково переезжают на S3.
    """

    __tablename__ = "chat_message_attachments"

    message_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("address_chat_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("stored_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    message: Mapped["AddressChatMessage"] = relationship(back_populates="attachments")
    file: Mapped["StoredFile"] = relationship()


class ChatRead(UUIDPKMixin, Base):
    """Докуда участник дочитал ветку.

    Строка на пару (ветка, пользователь); её отсутствие означает «не открывал
    ни разу», и тогда непрочитано всё. Хранить «прочитано» на каждом сообщении
    для каждого из троих участников было бы втрое больше строк ради того же
    ответа.
    """

    __tablename__ = "chat_reads"
    __table_args__ = (
        UniqueConstraint("chat_id", "user_id", name="uq_chat_reads_pair"),
    )

    chat_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("address_chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
