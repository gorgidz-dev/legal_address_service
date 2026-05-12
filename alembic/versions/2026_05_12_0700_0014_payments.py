"""payments table for CDEK Pay (SBP individuals first)

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("payer_type", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("amount_kopeks", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("pay_for", sa.Text(), nullable=False),
        sa.Column("cdek_access_key", sa.Text()),
        sa.Column("cdek_order_id", sa.BigInteger()),
        sa.Column("cdek_payment_id", sa.BigInteger()),
        sa.Column("qr_link", sa.Text()),
        sa.Column("qr_image_base64", sa.Text()),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("refunded_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("last_callback_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("initiated_by", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_payments_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by"],
            ["users.id"],
            name=op.f("fk_payments_initiated_by_users"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('pending','awaiting_user','succeeded','failed',"
            "'expired','cancelled','refund_requested','refunded')",
            name=op.f("ck_payments_status_valid"),
        ),
        sa.CheckConstraint(
            "payer_type IN ('individual','juridical')",
            name=op.f("ck_payments_payer_type_valid"),
        ),
        sa.CheckConstraint("provider IN ('cdek_pay')", name=op.f("ck_payments_provider_valid")),
        sa.CheckConstraint("amount_kopeks > 0", name=op.f("ck_payments_amount_positive")),
    )
    op.create_index("ix_payments_application_id", "payments", ["application_id"])
    op.create_index(
        "ix_payments_status_created",
        "payments",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_payments_cdek_access_key",
        "payments",
        ["cdek_access_key"],
        unique=True,
    )
    op.create_index(
        "ix_payments_cdek_payment_id",
        "payments",
        ["cdek_payment_id"],
        unique=True,
        postgresql_where=sa.text("cdek_payment_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_payments_cdek_payment_id", table_name="payments")
    op.drop_index("ix_payments_cdek_access_key", table_name="payments")
    op.drop_index("ix_payments_status_created", table_name="payments")
    op.drop_index("ix_payments_application_id", table_name="payments")
    op.drop_table("payments")
