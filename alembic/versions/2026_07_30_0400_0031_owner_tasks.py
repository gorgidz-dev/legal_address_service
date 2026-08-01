"""Поручения собственнику от оператора.

Часть работы собственника не привязана к заявке: «загрузите фото», «обновите
выписку». Чат для этого не годится — его читают один раз, и там нет ни срока,
ни признака «сделано».

Индекс (provider_id, status) — под главный запрос кабинета «мои открытые
задачи». Индекс по due_on частичный: срок необязателен.

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "owner_tasks",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "address_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("addresses.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column("created_by", PgUUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by", PgUUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_owner_tasks_provider_status", "owner_tasks", ["provider_id", "status"])
    op.create_index(
        "ix_owner_tasks_due_on",
        "owner_tasks",
        ["due_on"],
        postgresql_where=sa.text("due_on IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_owner_tasks_due_on", table_name="owner_tasks")
    op.drop_index("ix_owner_tasks_provider_status", table_name="owner_tasks")
    op.drop_table("owner_tasks")
