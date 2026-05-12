"""provider onboarding: link invitations <-> provider_connection_requests <-> providers

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invitations",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "invitations",
        sa.Column("source_request_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        op.f("fk_invitations_provider_id_providers"),
        "invitations",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_invitations_source_request_id_provider_connection_requests"),
        "invitations",
        "provider_connection_requests",
        ["source_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_invitations_provider_id",
        "invitations",
        ["provider_id"],
    )
    op.create_index(
        "ix_invitations_source_request_id",
        "invitations",
        ["source_request_id"],
    )

    op.add_column(
        "provider_connection_requests",
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True)),
    )
    op.create_foreign_key(
        op.f("fk_provider_connection_requests_invitation_id_invitations"),
        "provider_connection_requests",
        "invitations",
        ["invitation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_provider_connection_requests_invitation_id",
        "provider_connection_requests",
        ["invitation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_provider_connection_requests_invitation_id",
        table_name="provider_connection_requests",
    )
    op.drop_constraint(
        op.f("fk_provider_connection_requests_invitation_id_invitations"),
        "provider_connection_requests",
        type_="foreignkey",
    )
    op.drop_column("provider_connection_requests", "invitation_id")

    op.drop_index("ix_invitations_source_request_id", table_name="invitations")
    op.drop_index("ix_invitations_provider_id", table_name="invitations")
    op.drop_constraint(
        op.f("fk_invitations_source_request_id_provider_connection_requests"),
        "invitations",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_invitations_provider_id_providers"),
        "invitations",
        type_="foreignkey",
    )
    op.drop_column("invitations", "source_request_id")
    op.drop_column("invitations", "provider_id")
