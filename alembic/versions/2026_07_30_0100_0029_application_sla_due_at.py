"""Внутренний срок этапа заявки: applications.sla_due_at.

К этому моменту должен отработать собственник (согласовать заявку, загрузить
или переделать комплект) либо оператор (проверить загруженное). NULL означает
«ждать нечего»: заявка завершена, отменена или мяч на стороне клиента.

Индекс частичный — по строкам, где срок вообще стоит: очередь оператора
сортирует и подсвечивает именно их, а завершённых заявок в базе со временем
станет больше, чем активных.

Существующим заявкам срок не проставляется: он считается от момента входа в
статус, а этого момента для старых строк в базе нет. Первый же переход по
рабочему процессу его выставит.

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_applications_sla_due_at",
        "applications",
        ["sla_due_at"],
        postgresql_where=sa.text("sla_due_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_applications_sla_due_at", table_name="applications")
    op.drop_column("applications", "sla_due_at")
