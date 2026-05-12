"""session device metadata

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("session_type", sa.Text(), nullable=True))
    op.add_column("user_sessions", sa.Column("device_name", sa.Text(), nullable=True))
    op.add_column("user_sessions", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column("user_sessions", sa.Column("ip_address", sa.Text(), nullable=True))
    op.add_column(
        "user_sessions",
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_sessions", "last_seen_at")
    op.drop_column("user_sessions", "ip_address")
    op.drop_column("user_sessions", "user_agent")
    op.drop_column("user_sessions", "device_name")
    op.drop_column("user_sessions", "session_type")
