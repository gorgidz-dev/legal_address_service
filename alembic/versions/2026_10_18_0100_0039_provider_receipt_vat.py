"""Агентский чек: ставка НДС собственника

С 18.10.2026 (решение владельца) при оплате через площадку ООО действует как
агент собственника: в чеке позиция — услуга собственника, с признаком агента,
данными поставщика (ИНН, наименование, телефон собственника) и НДС
собственника, а не ООО (docs/tbank-acquiring.md §7, §10).

- providers.receipt_vat — ставка НДС собственника для чека: none (без НДС),
  vat0/5/7/10/22. NULL — не указана: оплату по адресам такого собственника
  не принимаем, пока админ её не задаст (ошибка в реквизитах чека — штраф).

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VAT_VALUES = ("none", "vat0", "vat5", "vat7", "vat10", "vat22")


def upgrade() -> None:
    op.add_column("providers", sa.Column("receipt_vat", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_providers_receipt_vat_valid"),
        "providers",
        "receipt_vat IS NULL OR receipt_vat IN (" + ", ".join(f"'{v}'" for v in VAT_VALUES) + ")",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_providers_receipt_vat_valid"), "providers", type_="check")
    op.drop_column("providers", "receipt_vat")
