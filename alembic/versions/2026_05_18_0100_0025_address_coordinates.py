"""addresses.latitude / longitude — координаты для показа на карте.

Заполняются геокодером Яндекса (app/services/yandex_geocoder.py). NULL —
адрес не геокодирован (геокодер не настроен или точка не найдена).

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "addresses",
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "addresses",
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("addresses", "longitude")
    op.drop_column("addresses", "latitude")
