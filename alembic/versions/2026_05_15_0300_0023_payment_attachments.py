"""payment_attachments — счёт и платёжное поручение, привязанные к платежу.

manual_invoice-флоу: собственник грузит счёт, клиент — платёжку, собственник
подтверждает поступление средств.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_attachments",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "payment_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "file_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stored_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "kind IN ('invoice', 'payment_order')",
            name="payment_attachments_kind_valid",
        ),
    )
    op.create_index(
        "ix_payment_attachments_payment_id", "payment_attachments", ["payment_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_attachments_payment_id", table_name="payment_attachments"
    )
    op.drop_table("payment_attachments")
