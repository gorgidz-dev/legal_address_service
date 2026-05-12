"""session refresh tokens

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("refresh_token_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("refresh_expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "user_sessions",
        sa.Column("last_refreshed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE UNIQUE INDEX ix_user_sessions_refresh_token_hash "
        "ON user_sessions (refresh_token_hash) "
        "WHERE refresh_token_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_sessions_refresh_token_hash")
    op.drop_column("user_sessions", "last_refreshed_at")
    op.drop_column("user_sessions", "refresh_expires_at")
    op.drop_column("user_sessions", "refresh_token_hash")
