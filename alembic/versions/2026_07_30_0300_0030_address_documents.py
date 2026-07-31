"""Хранилище правоустанавливающих документов по адресу.

Отдельная таблица, а не расширение egrn_extracts: та заточена под выписку
(номер выписки, файл подписи, хеш PDF, цепочка замен), и свидетельство о
собственности с доверенностью в неё не ложатся.

Файл лежит в общем stored_files, здесь только карточка документа. Ссылка на
файл с ON DELETE RESTRICT: карточку можно удалить, но не так, чтобы файл
остался сиротой в хранилище без единой ссылки.

Индекс по expires_at частичный: напоминалка ходит только по документам с
проставленным сроком, а у свидетельства о собственности срока нет.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "address_documents",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "address_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("addresses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("stored_files.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by", PgUUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_address_documents_address_id", "address_documents", ["address_id"])
    op.create_index(
        "ix_address_documents_expires_at",
        "address_documents",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_address_documents_expires_at", table_name="address_documents")
    op.drop_index("ix_address_documents_address_id", table_name="address_documents")
    op.drop_table("address_documents")
