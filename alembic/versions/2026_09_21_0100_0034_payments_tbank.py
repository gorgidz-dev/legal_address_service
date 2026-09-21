"""payments — провайдер Т-Банк, общие поля провайдера, один активный платёж на заявку

Эквайринг Т-Банка вместо так и не включённого CDEK Pay (docs/tbank-acquiring.md).

- provider: допустимо 'tbank'.
- Колонки, общие для провайдеров с внешним id: provider_payment_id (PaymentId
  банка — текстом, как число он теряет точность в JS), provider_status (сырой
  статус банка), provider_account (терминал, на котором создан платёж: после
  смены DEMO на боевой старые платежи боевому терминалу неизвестны),
  payment_url, provider_checked_at (троттлинг опроса GetState).
- Возвраты: refunded_kopeks — только подтверждённые банком; refund_attempts —
  счётчик наших попыток; refund_key — ExternalRequestId текущего возврата
  (повтор тем же ключом банк не исполнит дважды; NULL при refund_requested —
  возврат запущен мимо нас, из ЛК Т-Бизнеса).
- ux_payments_one_active_per_application: не больше одного платежа в
  pending/awaiting_user на заявку. Без него два одновременных «Оплатить»
  создавали два платежа, и клиент мог оплатить дважды. Перед созданием индекса
  лишние активные дубли (кроме самого свежего) переводятся в cancelled — на
  проде на 21.09.2026 платежей нет, это страховка для баз с демо-данными.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_payments_provider_valid"), "payments", type_="check")
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"),
        "payments",
        "provider IN ('cdek_pay', 'manual_invoice', 'tbank')",
    )

    op.add_column("payments", sa.Column("provider_payment_id", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("provider_status", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("provider_account", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("payment_url", sa.Text(), nullable=True))
    op.add_column(
        "payments",
        sa.Column("refunded_kopeks", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "payments",
        sa.Column("refund_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("payments", sa.Column("refund_key", sa.Text(), nullable=True))
    op.add_column(
        "payments",
        sa.Column("provider_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_payments_refunded_non_negative"),
        "payments",
        "refunded_kopeks >= 0 AND refunded_kopeks <= amount_kopeks",
    )

    op.create_index(
        "ux_payments_provider_payment_id",
        "payments",
        ["provider", "provider_payment_id"],
        unique=True,
        postgresql_where=sa.text("provider_payment_id IS NOT NULL"),
    )

    op.execute(
        """
        UPDATE payments SET status = 'cancelled'
        WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY application_id ORDER BY created_at DESC, id DESC
                ) AS rn
                FROM payments
                WHERE status IN ('pending', 'awaiting_user')
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_index(
        "ux_payments_one_active_per_application",
        "payments",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'awaiting_user')"),
    )


def downgrade() -> None:
    op.drop_index("ux_payments_one_active_per_application", table_name="payments")
    op.drop_index("ux_payments_provider_payment_id", table_name="payments")
    op.drop_constraint(op.f("ck_payments_refunded_non_negative"), "payments", type_="check")
    op.drop_column("payments", "provider_checked_at")
    op.drop_column("payments", "refund_key")
    op.drop_column("payments", "refund_attempts")
    op.drop_column("payments", "refunded_kopeks")
    op.drop_column("payments", "payment_url")
    op.drop_column("payments", "provider_account")
    op.drop_column("payments", "provider_status")
    op.drop_column("payments", "provider_payment_id")
    # Строки tbank нарушили бы старое ограничение — даунгрейд с ними невозможен
    # без решения, куда их девать; падаем явно, а не молча теряем платежи.
    op.drop_constraint(op.f("ck_payments_provider_valid"), "payments", type_="check")
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"),
        "payments",
        "provider IN ('cdek_pay', 'manual_invoice')",
    )
