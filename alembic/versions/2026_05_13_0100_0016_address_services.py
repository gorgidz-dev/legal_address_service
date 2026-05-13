"""address_services — таблица доп.услуг на адресе с прайсом собственника.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "address_services",
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
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.UniqueConstraint("address_id", "kind", name="uq_address_services_kind"),
        sa.CheckConstraint("price >= 0", name="address_services_price_non_negative"),
        sa.CheckConstraint(
            "kind IN ('guarantee_letter', 'lease_agreement', 'owner_confirmation')",
            name="address_services_kind_valid",
        ),
    )
    op.create_index(
        "ix_address_services_address_id",
        "address_services",
        ["address_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_address_services_address_id", table_name="address_services")
    op.drop_table("address_services")
