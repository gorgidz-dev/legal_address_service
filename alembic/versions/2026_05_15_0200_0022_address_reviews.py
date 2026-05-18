"""address_reviews — отзывы клиентов об адресах с рейтингом и модерацией.

Отзыв оставляет клиент с завершённой заявкой по адресу. Создаётся в статусе
pending, публично виден только после модерации (published). Один отзыв на
пару (адрес, клиент).

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "address_reviews",
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
        sa.Column(
            "application_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "moderated_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderation_note", sa.Text(), nullable=True),
        sa.Column("owner_reply", sa.Text(), nullable=True),
        sa.Column("owner_reply_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "address_id", "client_user_id", name="uq_address_reviews_pair"
        ),
        sa.CheckConstraint(
            "rating BETWEEN 1 AND 5", name="address_reviews_rating_range"
        ),
        sa.CheckConstraint("length(body) > 0", name="address_reviews_body_nonempty"),
    )
    op.create_index(
        "ix_address_reviews_address_id", "address_reviews", ["address_id"]
    )
    op.create_index(
        "ix_address_reviews_client_user_id", "address_reviews", ["client_user_id"]
    )
    op.create_index("ix_address_reviews_status", "address_reviews", ["status"])


def downgrade() -> None:
    op.drop_index("ix_address_reviews_status", table_name="address_reviews")
    op.drop_index(
        "ix_address_reviews_client_user_id", table_name="address_reviews"
    )
    op.drop_index("ix_address_reviews_address_id", table_name="address_reviews")
    op.drop_table("address_reviews")
