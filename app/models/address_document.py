"""Правоустанавливающие документы по адресу.

Отдельная модель, а не расширение EgrnExtract: та заточена под выписку —
номер выписки, файл подписи, хеш PDF и цепочка замен. Свидетельство о
собственности, договор с владельцем здания и доверенность в эту форму не
ложатся, а размывать её ради них значило бы сломать то, что уже работает.

Сам файл лежит в общем хранилище (stored_files) — том же, куда уходят
документы заявок. Здесь только карточка: что за документ, когда выдан и до
когда действует.

`expires_at` — то, ради чего всё затевалось: по нему собственнику уходит
напоминание, что документ пора обновить (services/document_expiry_reminders).
Дата необязательна: у свидетельства о собственности срока нет.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class AddressDocument(UUIDPKMixin, Base):
    __tablename__ = "address_documents"
    __table_args__ = (
        # Напоминалка ходит по документам с проставленным сроком.
        Index(
            "ix_address_documents_expires_at",
            "expires_at",
            postgresql_where=Text("expires_at IS NOT NULL"),
        ),
        Index("ix_address_documents_address_id", "address_id"),
    )

    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("addresses.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("stored_files.id", ondelete="RESTRICT"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    #: Название со слов собственника — «Свидетельство 77-АБ 123456».
    title: Mapped[str] = mapped_column(Text, nullable=False)

    issued_on: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
