"""auth, invitations, cloud file registry and payment documents

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk():
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text()))

    op.create_table(
        "invitations",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text()),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_invitations_created_by_users")),
        sa.CheckConstraint("role IN ('manager', 'lawyer', 'admin')", name=op.f("ck_invitations_role_valid")),
    )
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_index("ix_invitations_email", "invitations", ["email"])

    op.create_table(
        "user_sessions",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users")),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.create_table(
        "stored_files",
        _uuid_pk(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True)),
        sa.Column("application_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_backend", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("public_url", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_files")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_stored_files_client_id_clients")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], name=op.f("fk_stored_files_application_id_applications")),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name=op.f("fk_stored_files_uploaded_by_users")),
    )
    op.create_index("ix_stored_files_client_id", "stored_files", ["client_id", "created_at"])
    op.create_index("ix_stored_files_application_id", "stored_files", ["application_id", "created_at"])
    op.create_index("ix_stored_files_kind", "stored_files", ["kind"])

    op.create_table(
        "payment_documents",
        _uuid_pk(),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_date", sa.Date()),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_documents")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_payment_documents_client_id_clients")),
        sa.ForeignKeyConstraint(["file_id"], ["stored_files.id"], name=op.f("fk_payment_documents_file_id_stored_files")),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name=op.f("fk_payment_documents_uploaded_by_users")),
    )
    op.create_index("ix_payment_documents_client_id", "payment_documents", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payment_documents_client_id", table_name="payment_documents")
    op.drop_table("payment_documents")
    op.drop_index("ix_stored_files_kind", table_name="stored_files")
    op.drop_index("ix_stored_files_application_id", table_name="stored_files")
    op.drop_index("ix_stored_files_client_id", table_name="stored_files")
    op.drop_table("stored_files")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_table("invitations")
    op.drop_column("users", "password_hash")
