"""marketplace core roles, moderation and events

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


APPLICATION_STATUSES = (
    "'draft', 'guarantee_issued', 'awaiting_contract', 'contract_signed', "
    "'active', 'expired', 'terminated', 'awaiting_payment', 'paid', "
    "'admin_review', 'needs_client_fix', 'assigned_to_owner', "
    "'accepted_by_owner', 'rejected_by_owner', 'documents_preparing', "
    "'documents_uploaded', 'documents_review', 'documents_revision', "
    "'ready_for_client', 'completed', 'cancelled', 'dispute', "
    "'refund_pending', 'refunded'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.add_column("users", sa.Column("provider_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_users_provider_id_providers"),
        "users",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_provider_id", "users", ["provider_id"])
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
    )

    op.drop_constraint(op.f("ck_invitations_role_valid"), "invitations", type_="check")
    op.create_check_constraint(
        op.f("ck_invitations_role_valid"),
        "invitations",
        "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
    )

    op.add_column(
        "addresses",
        sa.Column("publication_status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
    )
    op.add_column("addresses", sa.Column("published_at", sa.TIMESTAMP(timezone=True)))
    op.add_column("addresses", sa.Column("moderation_comment", sa.Text()))
    op.add_column("addresses", sa.Column("moderated_by", postgresql.UUID(as_uuid=True)))
    op.add_column("addresses", sa.Column("moderated_at", sa.TIMESTAMP(timezone=True)))
    op.create_foreign_key(
        op.f("fk_addresses_moderated_by_users"),
        "addresses",
        "users",
        ["moderated_by"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_addresses_publication_status_valid"),
        "addresses",
        "publication_status IN ('draft', 'moderation', 'published', 'rejected', 'archived')",
    )

    op.drop_constraint(op.f("ck_applications_status_valid"), "applications", type_="check")
    op.create_check_constraint(
        op.f("ck_applications_status_valid"),
        "applications",
        f"status IN ({APPLICATION_STATUSES})",
    )

    op.create_table(
        "provider_connection_requests",
        _uuid_pk(),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("address_count", sa.Integer()),
        sa.Column("comment", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'new'"), nullable=False),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_connection_requests")),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_provider_connection_requests_reviewed_by_users"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'reviewing', 'invited', 'rejected')",
            name=op.f("ck_provider_connection_requests_status_valid"),
        ),
        sa.CheckConstraint(
            "address_count IS NULL OR address_count >= 0",
            name=op.f("ck_provider_connection_requests_address_count_non_negative"),
        ),
    )
    op.create_index(
        "ix_provider_connection_requests_status_created",
        "provider_connection_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_provider_connection_requests_contact_email",
        "provider_connection_requests",
        ["contact_email"],
    )

    op.create_table(
        "application_events",
        _uuid_pk(),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            ondelete="CASCADE",
            name=op.f("fk_application_events_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_application_events_created_by_users")),
        sa.CheckConstraint(
            "kind IN ('created', 'status_changed', 'comment_added', 'document_uploaded', "
            "'document_approved', 'correction_requested', 'dispute_opened', 'cancelled')",
            name=op.f("ck_application_events_kind_valid"),
        ),
        sa.CheckConstraint(
            "audience IN ('client', 'owner', 'admin')",
            name=op.f("ck_application_events_audience_valid"),
        ),
    )
    op.create_index(
        "ix_application_events_application_created",
        "application_events",
        ["application_id", "created_at"],
    )
    op.create_index(
        "ix_application_events_audience_read",
        "application_events",
        ["audience", "is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_application_events_audience_read", table_name="application_events")
    op.drop_index("ix_application_events_application_created", table_name="application_events")
    op.drop_table("application_events")

    op.drop_index("ix_provider_connection_requests_contact_email", table_name="provider_connection_requests")
    op.drop_index("ix_provider_connection_requests_status_created", table_name="provider_connection_requests")
    op.drop_table("provider_connection_requests")

    op.drop_constraint(op.f("ck_applications_status_valid"), "applications", type_="check")
    op.create_check_constraint(
        op.f("ck_applications_status_valid"),
        "applications",
        "status IN ('draft', 'guarantee_issued', 'awaiting_contract', "
        "'contract_signed', 'active', 'expired', 'terminated')",
    )

    op.drop_constraint(op.f("ck_addresses_publication_status_valid"), "addresses", type_="check")
    op.drop_constraint(op.f("fk_addresses_moderated_by_users"), "addresses", type_="foreignkey")
    op.drop_column("addresses", "moderated_at")
    op.drop_column("addresses", "moderated_by")
    op.drop_column("addresses", "moderation_comment")
    op.drop_column("addresses", "published_at")
    op.drop_column("addresses", "publication_status")

    op.drop_constraint(op.f("ck_invitations_role_valid"), "invitations", type_="check")
    op.create_check_constraint(
        op.f("ck_invitations_role_valid"),
        "invitations",
        "role IN ('manager', 'lawyer', 'admin')",
    )

    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.drop_index("ix_users_provider_id", table_name="users")
    op.drop_constraint(op.f("fk_users_provider_id_providers"), "users", type_="foreignkey")
    op.drop_column("users", "provider_id")
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('manager', 'lawyer', 'admin')",
    )
