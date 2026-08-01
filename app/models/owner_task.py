"""Поручение собственнику от оператора.

Зачем отдельная сущность. Часть работы собственника не привязана к заявке:
«загрузите фото помещения», «обновите выписку», «подтвердите доверенность».
Повесить это на заявку нельзя — заявки может не быть вовсе, а писать в чат
значит потерять: чат читают один раз, и там нет ни срока, ни признака
«сделано».

Задачу ставит оператор, закрывает собственник. Обратное направление
(собственник ставит задачу оператору) намеренно не заведено: для этого есть
чат по адресу, и второй канал переписки только размоет ответственность.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class OwnerTask(UUIDPKMixin, Base):
    __tablename__ = "owner_tasks"
    __table_args__ = (
        # Кабинет собственника открывает свои открытые задачи — это его главный
        # запрос по таблице.
        Index("ix_owner_tasks_provider_status", "provider_id", "status"),
        Index(
            "ix_owner_tasks_due_on",
            "due_on",
            postgresql_where=Text("due_on IS NOT NULL"),
        ),
    )

    provider_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Задача может быть про конкретный адрес, а может — про организацию вообще.
    address_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("addresses.id", ondelete="CASCADE")
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'open'")
    due_on: Mapped[Optional[date]] = mapped_column(Date)

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )
