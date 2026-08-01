"""Базовый класс ORM-моделей. Naming convention нужен Alembic для стабильных имён."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPKMixin:
    """Первичный ключ UUID.

    Значение генерируется с обеих сторон: `default` — питоном при вставке через
    ORM, `server_default` — базой при вставке сырым SQL. Дублирование не
    избыточно. Пока ключ держался только на server_default, миграция, забывшая
    `gen_random_uuid()`, давала таблицу, которая проходила все тесты и падала
    NotNullViolation на первой же настоящей записи — так случилось с
    address_documents, owner_tasks и таблицами чата (исправлено миграцией 0033).
    Питоновский default делает такую ошибку невозможной, а тест
    tests/test_migrations_uuid_default.py всё равно ловит её в схеме.
    """

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        default=uuid4,
        server_default=func.gen_random_uuid(),
        primary_key=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
