"""incoming webhooks audit + idempotency store

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incoming_webhooks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text()),
        sa.Column("raw_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incoming_webhooks")),
    )
    op.create_index(
        "ix_incoming_webhooks_provider_external_id",
        "incoming_webhooks",
        ["provider", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incoming_webhooks_provider_external_id",
        table_name="incoming_webhooks",
    )
    op.drop_table("incoming_webhooks")
