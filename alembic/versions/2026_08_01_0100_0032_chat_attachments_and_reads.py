"""Вложения в чате и отметка «докуда дочитал».

Три изменения:

1. `chat_message_attachments` — файл, прикреплённый к сообщению. Сам файл
   ложится в stored_files, как документ заявки: одно хранилище, один переезд
   на S3, один способ отдавать.

2. `chat_reads` — докуда каждый участник дочитал ветку. Без этого в переписке
   на троих не видно, что нового.

3. Снимается CHECK «тело непустое». Сообщение из одного файла без единого
   слова — нормальный случай, а выразить «текст ИЛИ вложение» на уровне БД
   нельзя: дочерняя таблица ей не видна. Проверку держит сервис
   (services/chat_attachments.py), на неё есть тест.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_message_attachments",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("address_chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("stored_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            PgUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_chat_message_attachments_message_id",
        "chat_message_attachments",
        ["message_id"],
    )

    op.create_table(
        "chat_reads",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "chat_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("address_chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            PgUUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chat_id", "user_id", name="uq_chat_reads_pair"),
    )
    op.create_index("ix_chat_reads_chat_id", "chat_reads", ["chat_id"])

    # Пустое тело разрешаем только вместе с вложением — см. шапку файла.
    op.drop_constraint(
        "address_chat_messages_body_nonempty",
        "address_chat_messages",
        type_="check",
    )
    op.alter_column(
        "address_chat_messages",
        "body",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="",
    )


def downgrade() -> None:
    # Сообщения без текста (одни вложения) вернуть под старый CHECK нельзя —
    # он их отвергнет. Проставляем им заглушку, иначе откат упадёт на данных.
    op.execute(
        "UPDATE address_chat_messages SET body = 'Файл' WHERE length(body) = 0"
    )
    op.alter_column(
        "address_chat_messages",
        "body",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=None,
    )
    op.create_check_constraint(
        "address_chat_messages_body_nonempty",
        "address_chat_messages",
        "length(body) > 0",
    )
    op.drop_index("ix_chat_reads_chat_id", table_name="chat_reads")
    op.drop_table("chat_reads")
    op.drop_index(
        "ix_chat_message_attachments_message_id",
        table_name="chat_message_attachments",
    )
    op.drop_table("chat_message_attachments")
