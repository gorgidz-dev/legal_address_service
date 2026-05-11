"""address photos with moderation

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "address_photos",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("address_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_backend", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "moderation_status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("moderation_comment", sa.Text()),
        sa.Column("moderated_by", postgresql.UUID(as_uuid=True)),
        sa.Column("moderated_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("is_main", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "sort_order",
            sa.SmallInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_address_photos")),
        sa.ForeignKeyConstraint(
            ["address_id"],
            ["addresses.id"],
            ondelete="CASCADE",
            name=op.f("fk_address_photos_address_id_addresses"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name=op.f("fk_address_photos_uploaded_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["moderated_by"],
            ["users.id"],
            name=op.f("fk_address_photos_moderated_by_users"),
        ),
        sa.CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected')",
            name=op.f("ck_address_photos_moderation_status_valid"),
        ),
        sa.CheckConstraint(
            "size_bytes > 0",
            name=op.f("ck_address_photos_size_bytes_positive"),
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0",
            name=op.f("ck_address_photos_dimensions_positive"),
        ),
        sa.CheckConstraint(
            "sort_order >= 0",
            name=op.f("ck_address_photos_sort_order_non_negative"),
        ),
    )
    op.create_index(
        "ix_address_photos_address_id",
        "address_photos",
        ["address_id", "moderation_status"],
    )
    op.create_index(
        "ix_address_photos_moderation_status",
        "address_photos",
        ["moderation_status", "created_at"],
    )
    # Только одно главное фото на адрес — и только если оно одобрено.
    op.execute(
        "CREATE UNIQUE INDEX ix_address_photos_main_per_address "
        "ON address_photos (address_id) "
        "WHERE is_main IS TRUE AND moderation_status = 'approved'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_address_photos_main_per_address")
    op.drop_index("ix_address_photos_moderation_status", table_name="address_photos")
    op.drop_index("ix_address_photos_address_id", table_name="address_photos")
    op.drop_table("address_photos")
