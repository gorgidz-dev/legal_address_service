"""fns_offices — справочник ИФНС (регион/город/код) + addresses.fns_office_id.

Иерархия каталога Регион → Город → ИФНС строится из справочника. Адрес
ссылается на инспекцию через fns_office_id; регион и город — атрибуты ИФНС.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fns_offices",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_number", sa.Integer(), nullable=True),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("code", name="uq_fns_offices_code"),
    )
    op.create_index(
        "ix_fns_offices_region_city", "fns_offices", ["region", "city"]
    )

    op.add_column(
        "addresses",
        sa.Column(
            "fns_office_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fns_offices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_addresses_fns_office_id", "addresses", ["fns_office_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_addresses_fns_office_id", table_name="addresses")
    op.drop_column("addresses", "fns_office_id")
    op.drop_index("ix_fns_offices_region_city", table_name="fns_offices")
    op.drop_table("fns_offices")
