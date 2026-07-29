"""Удаление генерации документов: generated_documents, guarantee_letters, document_templates.

Генератор гарантийных писем и договоров попал в проект из соседней утилиты и
к продукту отношения не имеет: документы готовит собственник, сервис их
принимает и проверяет. На проде фича не отработала ни разу — 0 строк во всех
трёх таблицах при 9 заявках.

downgrade возвращает структуру, но не данные: восстанавливать нечего.

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Порядок важен: generated_documents ссылается на две другие таблицы.
    op.drop_table("generated_documents")
    op.drop_table("guarantee_letters")
    op.drop_table("document_templates")


def downgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "guarantee_letters",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "generated_documents",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("docx_url", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("zip_url", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
