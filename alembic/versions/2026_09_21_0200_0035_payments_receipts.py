"""payments — чеки 54-ФЗ: снимок чека предоплаты и состояние закрывающего чека

Два чека на оплату картой/СБП через Т-Банк (docs/tbank-acquiring.md §7, §10):
«предоплата 100%» уходит в банк вместе с Init, «полный расчёт» — методом
SendClosingReceipt, когда клиент получает документы.

- receipt: Receipt, отправленный в Init. Закрывающий чек обязан повторять его
  позиции, поэтому храним снимок, а не пересобираем по текущим настройкам.
- closing_receipt_status: NULL — закрывающий не нужен (или ещё рано);
  due — пора отправить; sending — отправка идёт (занята, чтобы крон и
  фоновая задача не отправили дважды); sent — банк принял; failed — банк явно
  отказал, можно повторить; unknown — связь оборвалась, неизвестно, ушёл ли
  чек (у метода нет ключа идемпотентности — повтор вслепую мог бы пробить
  второй чек, поэтому решает админ по ЛК).
- closing_receipt_attempts / _at / _error — для повторов и разбора.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("receipt", postgresql.JSONB(), nullable=True))
    op.add_column("payments", sa.Column("closing_receipt_status", sa.Text(), nullable=True))
    op.add_column(
        "payments",
        sa.Column(
            "closing_receipt_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.add_column(
        "payments", sa.Column("closing_receipt_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("payments", sa.Column("closing_receipt_error", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_payments_closing_receipt_status_valid"),
        "payments",
        "closing_receipt_status IS NULL OR closing_receipt_status IN "
        "('due', 'sending', 'sent', 'failed', 'unknown')",
    )
    # Фоновая сверка ищет чеки, которые пора (до)отправить, — их единицы.
    op.create_index(
        "ix_payments_closing_receipt_pending",
        "payments",
        ["closing_receipt_status"],
        postgresql_where=sa.text("closing_receipt_status IN ('due', 'sending', 'failed')"),
    )


def downgrade() -> None:
    op.drop_index("ix_payments_closing_receipt_pending", table_name="payments")
    op.drop_constraint(
        op.f("ck_payments_closing_receipt_status_valid"), "payments", type_="check"
    )
    op.drop_column("payments", "closing_receipt_error")
    op.drop_column("payments", "closing_receipt_at")
    op.drop_column("payments", "closing_receipt_attempts")
    op.drop_column("payments", "closing_receipt_status")
    op.drop_column("payments", "receipt")
