"""auth attempts table for rate limiting

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("key_type", sa.Text(), nullable=False),
        sa.Column("attempt_key", sa.Text(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_attempts")),
        sa.CheckConstraint(
            "key_type IN ('email', 'ip')",
            name=op.f("ck_auth_attempts_key_type_valid"),
        ),
    )
    op.create_index(
        "ix_auth_attempts_lookup",
        "auth_attempts",
        ["scope", "key_type", "attempt_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_lookup", table_name="auth_attempts")
    op.drop_table("auth_attempts")
