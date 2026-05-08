"""application contacts and company display fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("company_name", sa.Text()))
    op.add_column("applications", sa.Column("contact_name", sa.Text()))
    op.add_column("applications", sa.Column("contact_phone", sa.Text()))
    op.add_column("applications", sa.Column("contact_email", sa.Text()))

    op.execute(
        """
        UPDATE applications
        SET company_name = planned_client_name
        WHERE type = 'initial_registration' AND company_name IS NULL
        """
    )
    op.execute(
        """
        UPDATE applications a
        SET company_name = c.short_name
        FROM clients c
        WHERE a.client_id = c.id
          AND a.type = 'address_change'
          AND a.company_name IS NULL
        """
    )
    op.create_index("ix_applications_company_name", "applications", ["company_name"])


def downgrade() -> None:
    op.drop_index("ix_applications_company_name", table_name="applications")
    op.drop_column("applications", "contact_email")
    op.drop_column("applications", "contact_phone")
    op.drop_column("applications", "contact_name")
    op.drop_column("applications", "company_name")
