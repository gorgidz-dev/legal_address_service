"""Статус-трекер: расписка ИФНС и ожидаемая дата регистрации

Этап 6 дорожной карты (docs/roadmap-2026-07-feedback.md). После выдачи
документов клиент подаёт их в ИФНС сам и загружает в кабинет расписку о
приёме документов (stored_files, kind = ifns_receipt) с датой предстоящей
регистрации из неё. Прогноз в трекере строится от этой даты.

- applications.registration_expected_on — дата регистрации из расписки
  (вводит клиент; распознавать скан не нужно);
- applications.ifns_receipt_uploaded_at — когда загружена последняя расписка
  (чтобы читать трекер без выборки по stored_files).

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("registration_expected_on", sa.Date(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("ifns_receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Ежедневное напоминание «пора сверить регистрацию» ищет заявки по этой дате.
    op.create_index(
        "ix_applications_registration_expected_on",
        "applications",
        ["registration_expected_on"],
        postgresql_where=sa.text(
            "registration_expected_on IS NOT NULL AND registration_confirmed_at IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_applications_registration_expected_on", table_name="applications")
    op.drop_column("applications", "ifns_receipt_uploaded_at")
    op.drop_column("applications", "registration_expected_on")
