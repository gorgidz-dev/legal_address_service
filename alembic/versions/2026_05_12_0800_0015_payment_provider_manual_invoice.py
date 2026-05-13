"""payments.provider — добавить 'manual_invoice' (юр.лица, ручное подтверждение)

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_payments_provider_valid"), "payments", type_="check")
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"),
        "payments",
        "provider IN ('cdek_pay', 'manual_invoice')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_payments_provider_valid"), "payments", type_="check")
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"),
        "payments",
        "provider IN ('cdek_pay')",
    )
