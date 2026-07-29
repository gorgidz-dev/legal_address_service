"""addresses.amenities — характеристики помещения (метро, парковка, охрана…).

Список строк из app.enums.AddressAmenity. Отмечает собственник; сервис их не
проверяет, поэтому в карточке они подписаны как слова собственника.

Пустой массив, а не NULL: «характеристик нет» и «собственник ещё не заполнял»
для витрины одно и то же, а NULL заставлял бы каждый запрос помнить про
coalesce.

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY


revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "addresses",
        sa.Column(
            "amenities",
            ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    # Фильтр «рядом с метро» в каталоге — впереди; без индекса он пойдёт
    # seq-скану по всем опубликованным адресам.
    op.create_index(
        "ix_addresses_amenities",
        "addresses",
        ["amenities"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_addresses_amenities", table_name="addresses")
    op.drop_column("addresses", "amenities")
