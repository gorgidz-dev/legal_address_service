"""Возвращает gen_random_uuid() четырём таблицам, где его не было.

Первичный ключ в проекте генерирует база (UUIDPKMixin.server_default). Четыре
таблицы, созданные 30.07–01.08, объявили `id` без этого умолчания: миграции
писались вручную, а модель об этом умолчании не напоминала. Такая таблица
проходит все тесты — они работают на подставных сессиях — и падает
NotNullViolation на первой настоящей вставке.

Найдено смоук-прогоном чата 01.08.2026 на отдельной базе. Затронуты:
address_documents (0030), owner_tasks (0031), chat_message_attachments и
chat_reads (0032) — то есть «Документы адреса», «Задачи собственнику» и
вложения в переписке не работали бы вовсе.

Параллельно UUIDPKMixin получил питоновский default=uuid4, так что ORM больше
не зависит от умолчания в схеме. Эта миграция приводит в порядок саму схему —
для вставок сырым SQL и для того, чтобы схема соответствовала модели.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "address_documents",
    "owner_tasks",
    "chat_message_attachments",
    "chat_reads",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT")
