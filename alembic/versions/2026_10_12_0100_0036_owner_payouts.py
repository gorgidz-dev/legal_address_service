"""Выплаты собственникам и подтверждение регистрации компании клиента

Модель денег (CLAUDE.md, «Как устроены деньги»): когда платёж принимает
площадка (эквайринг), она перечисляет собственнику цену за вычетом своей
комиссии — и только после успешной регистрации компании клиента по адресу
(решение владельца 12.10.2026).

- providers.commission_percent — процент комиссии площадки у собственника;
  NULL — берётся OWNER_COMMISSION_DEFAULT_PERCENT из настроек.
- applications.registration_* — ИНН зарегистрированной компании (сообщает
  клиент или вводит админ), снимок сверки с ЕГРЮЛ (DaData) и кто/когда
  подтвердил регистрацию.
- owner_payouts — выплата по оплаченной через площадку заявке:
  awaiting_registration → due (регистрация подтверждена) → paid (админ
  перевёл деньги и отметил); cancelled — отменена (возврат, отмена заявки).
  Процент и суммы — снимок на момент оплаты: поздняя смена процента у
  собственника старые сделки не трогает.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "providers", sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_providers_commission_percent_range"),
        "providers",
        "commission_percent IS NULL OR (commission_percent >= 0 AND commission_percent < 100)",
    )

    op.add_column("applications", sa.Column("registration_inn", sa.Text(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("registration_inn_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("registration_check", postgresql.JSONB(none_as_null=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("registration_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column(
            "registration_confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "owner_payouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("providers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default=sa.text("'awaiting_registration'")
        ),
        sa.Column("gross_kopeks", sa.BigInteger(), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("commission_kopeks", sa.BigInteger(), nullable=True),
        sa.Column("payout_kopeks", sa.BigInteger(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "paid_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("bank_reference", sa.Text(), nullable=True),
        sa.Column("payee", postgresql.JSONB(none_as_null=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('awaiting_registration', 'due', 'paid', 'cancelled')",
            name=op.f("ck_owner_payouts_status_valid"),
        ),
        sa.CheckConstraint("gross_kopeks > 0", name=op.f("ck_owner_payouts_gross_positive")),
        # Суммы либо ещё не посчитаны (процент не задан), либо сходятся до копейки.
        sa.CheckConstraint(
            "(commission_percent IS NULL AND commission_kopeks IS NULL AND payout_kopeks IS NULL)"
            " OR (commission_percent >= 0 AND commission_percent < 100"
            " AND commission_kopeks >= 0 AND payout_kopeks > 0"
            " AND commission_kopeks + payout_kopeks = gross_kopeks)",
            name=op.f("ck_owner_payouts_split_consistent"),
        ),
        # К выплате и выплаченное — только с посчитанной суммой.
        sa.CheckConstraint(
            "status IN ('awaiting_registration', 'cancelled') OR payout_kopeks IS NOT NULL",
            name=op.f("ck_owner_payouts_amount_known"),
        ),
        sa.CheckConstraint(
            "status <> 'paid' OR (paid_on IS NOT NULL AND paid_at IS NOT NULL"
            " AND bank_reference IS NOT NULL)",
            name=op.f("ck_owner_payouts_paid_complete"),
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' OR cancel_reason IS NOT NULL",
            name=op.f("ck_owner_payouts_cancel_reason"),
        ),
    )
    op.create_index("ux_owner_payouts_payment_id", "owner_payouts", ["payment_id"], unique=True)
    # Одна живая выплата на заявку: повторная оплата той же заявки не плодит вторую.
    op.create_index(
        "ux_owner_payouts_one_active_per_application",
        "owner_payouts",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_index("ix_owner_payouts_status", "owner_payouts", ["status", "created_at"])
    op.create_index("ix_owner_payouts_provider", "owner_payouts", ["provider_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text("SELECT count(*) FROM owner_payouts")).scalar_one()
    if count:
        raise RuntimeError(
            f"В owner_payouts {count} строк — это учёт денег собственников. "
            "Даунгрейд удалил бы его; выгрузите и удалите строки вручную, если это нужно."
        )
    op.drop_index("ix_owner_payouts_provider", table_name="owner_payouts")
    op.drop_index("ix_owner_payouts_status", table_name="owner_payouts")
    op.drop_index("ux_owner_payouts_one_active_per_application", table_name="owner_payouts")
    op.drop_index("ux_owner_payouts_payment_id", table_name="owner_payouts")
    op.drop_table("owner_payouts")
    op.drop_column("applications", "registration_confirmed_by")
    op.drop_column("applications", "registration_confirmed_at")
    op.drop_column("applications", "registration_check")
    op.drop_column("applications", "registration_inn_submitted_at")
    op.drop_column("applications", "registration_inn")
    op.drop_constraint(
        op.f("ck_providers_commission_percent_range"), "providers", type_="check"
    )
    op.drop_column("providers", "commission_percent")
