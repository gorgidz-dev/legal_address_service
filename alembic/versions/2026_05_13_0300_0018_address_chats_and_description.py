"""addresses.description + address_chats + address_chat_messages.

Описание адреса заполняет собственник; чат — приват pair (адрес × клиент).

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("addresses", sa.Column("description", sa.Text(), nullable=True))

    op.create_table(
        "address_chats",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "address_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("addresses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("address_id", "client_user_id", name="uq_address_chats_pair"),
    )
    op.create_index("ix_address_chats_address_id", "address_chats", ["address_id"])
    op.create_index("ix_address_chats_client_user_id", "address_chats", ["client_user_id"])

    op.create_table(
        "address_chat_messages",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chat_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("address_chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("length(body) > 0", name="address_chat_messages_body_nonempty"),
    )
    op.create_index("ix_address_chat_messages_chat_id", "address_chat_messages", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_address_chat_messages_chat_id", table_name="address_chat_messages")
    op.drop_table("address_chat_messages")
    op.drop_index("ix_address_chats_client_user_id", table_name="address_chats")
    op.drop_index("ix_address_chats_address_id", table_name="address_chats")
    op.drop_table("address_chats")
    op.drop_column("addresses", "description")
