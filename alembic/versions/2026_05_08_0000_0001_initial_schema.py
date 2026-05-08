"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-08

Создаёт всю исходную схему: users, providers, addresses, egrn_extracts,
clients, applications, contracts, guarantee_letters, document_templates,
generated_documents + триггеры обновления updated_at.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk():
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _ts_columns():
    return [
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ----- users -----
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint("role IN ('manager', 'lawyer', 'admin')", name=op.f("ck_users_role_valid")),
    )

    # ----- providers -----
    op.create_table(
        "providers",
        _uuid_pk(),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=False),
        sa.Column("inn", sa.Text()),
        sa.Column("kpp", sa.Text()),
        sa.Column("ogrn", sa.Text()),
        sa.Column("okpo", sa.Text()),
        sa.Column("legal_address", sa.Text()),
        sa.Column("signatory_name", sa.Text()),
        sa.Column("signatory_position", sa.Text()),
        sa.Column("signatory_basis", sa.Text()),
        sa.Column("signatory_name_genitive", sa.Text()),
        sa.Column("signatory_position_genitive", sa.Text()),
        sa.Column("signatory_initials", sa.Text()),
        sa.Column("bank_name", sa.Text()),
        sa.Column("settlement_account", sa.Text()),
        sa.Column("corr_account", sa.Text()),
        sa.Column("bik", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
        sa.UniqueConstraint("code", name=op.f("uq_providers_code")),
        sa.CheckConstraint("inn IS NULL OR length(inn) IN (10, 12)", name=op.f("ck_providers_inn_length")),
        sa.CheckConstraint("ogrn IS NULL OR length(ogrn) IN (13, 15)", name=op.f("ck_providers_ogrn_length")),
        sa.CheckConstraint("bik IS NULL OR length(bik) = 9", name=op.f("ck_providers_bik_length")),
    )
    op.create_index("ix_providers_is_active", "providers", ["is_active"])

    # ----- addresses -----
    op.create_table(
        "addresses",
        _uuid_pk(),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_address", sa.Text(), nullable=False),
        sa.Column("room_number", sa.Text()),
        sa.Column("cadastral_number", sa.Text(), nullable=False),
        sa.Column("ownership_doc", sa.Text(), nullable=False),
        sa.Column("ownership_doc_short", sa.Text(), nullable=False),
        sa.Column("ownership_doc_pages", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("price_6m", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_11m", sa.Numeric(12, 2), nullable=False),
        sa.Column("correspondence_price", sa.Numeric(12, 2)),
        sa.Column("fns_number", sa.SmallInteger()),
        sa.Column("fns_city", sa.Text()),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notes", sa.Text()),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_addresses")),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="RESTRICT", name=op.f("fk_addresses_provider_id_providers")),
        sa.CheckConstraint("price_6m > 0 AND price_11m > 0", name=op.f("ck_addresses_prices_positive")),
        sa.CheckConstraint("ownership_doc_pages > 0", name=op.f("ck_addresses_pages_positive")),
    )
    op.create_index("ix_addresses_provider_id", "addresses", ["provider_id", "is_available"])

    # ----- egrn_extracts -----
    op.create_table(
        "egrn_extracts",
        _uuid_pk(),
        sa.Column("address_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pdf_file_url", sa.Text(), nullable=False),
        sa.Column("signature_file_url", sa.Text()),
        sa.Column("extract_number", sa.Text()),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("pdf_sha256", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("notes", sa.Text()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_egrn_extracts")),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"], ondelete="RESTRICT", name=op.f("fk_egrn_extracts_address_id_addresses")),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["egrn_extracts.id"], name=op.f("fk_egrn_extracts_replaced_by_id_egrn_extracts")),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name=op.f("fk_egrn_extracts_uploaded_by_users")),
        sa.CheckConstraint("expires_at > issue_date", name=op.f("ck_egrn_extracts_expiry_after_issue")),
    )
    op.create_index(
        "uniq_current_egrn_per_address", "egrn_extracts", ["address_id"],
        unique=True, postgresql_where=sa.text("is_current = true"),
    )
    op.create_index(
        "ix_egrn_extracts_address_id", "egrn_extracts", ["address_id", sa.text("issue_date DESC")],
    )

    # ----- clients -----
    op.create_table(
        "clients",
        _uuid_pk(),
        sa.Column("inn", sa.Text(), nullable=False),
        sa.Column("kpp", sa.Text()),
        sa.Column("ogrn", sa.Text()),
        sa.Column("ogrn_date", sa.Date()),
        sa.Column("okpo", sa.Text()),
        sa.Column("okved_main_code", sa.Text()),
        sa.Column("okved_main_name", sa.Text()),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=False),
        sa.Column("legal_address", sa.Text()),
        sa.Column("kladr_id", sa.Text()),
        sa.Column("signatory_name", sa.Text()),
        sa.Column("signatory_position", sa.Text()),
        sa.Column("signatory_basis", sa.Text(), server_default=sa.text("'Устава'"), nullable=False),
        sa.Column("signatory_name_genitive", sa.Text()),
        sa.Column("signatory_position_genitive", sa.Text()),
        sa.Column("signatory_initials", sa.Text()),
        sa.Column("bank_name", sa.Text()),
        sa.Column("settlement_account", sa.Text()),
        sa.Column("corr_account", sa.Text()),
        sa.Column("bik", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("phone", sa.Text()),
        sa.Column("egrul_status", sa.Text()),
        sa.Column("last_dadata_refresh_at", sa.TIMESTAMP(timezone=True)),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
        sa.UniqueConstraint("inn", name=op.f("uq_clients_inn")),
        sa.CheckConstraint("length(inn) = 10", name=op.f("ck_clients_inn_length")),
        sa.CheckConstraint("ogrn IS NULL OR length(ogrn) = 13", name=op.f("ck_clients_ogrn_length")),
        sa.CheckConstraint("kpp IS NULL OR length(kpp) = 9", name=op.f("ck_clients_kpp_length")),
    )

    # ----- applications -----
    op.create_table(
        "applications",
        _uuid_pk(),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True)),
        sa.Column("planned_client_name", sa.Text()),
        sa.Column("term_months", sa.SmallInteger()),
        sa.Column("has_correspondence_service", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notice_period", sa.Text()),
        sa.Column("contract_city", sa.Text()),
        sa.Column("fns_number", sa.SmallInteger()),
        sa.Column("fns_city", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("expires_at", sa.Date()),
        sa.Column("parent_application_id", postgresql.UUID(as_uuid=True)),
        *_ts_columns(),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], name=op.f("fk_applications_provider_id_providers")),
        sa.ForeignKeyConstraint(["address_id"], ["addresses.id"], name=op.f("fk_applications_address_id_addresses")),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], name=op.f("fk_applications_client_id_clients")),
        sa.ForeignKeyConstraint(["parent_application_id"], ["applications.id"], name=op.f("fk_applications_parent_application_id_applications")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_applications_created_by_users")),
        sa.CheckConstraint("type IN ('initial_registration', 'address_change')", name=op.f("ck_applications_type_valid")),
        sa.CheckConstraint("term_months IS NULL OR term_months IN (6, 11)", name=op.f("ck_applications_term_months_valid")),
        sa.CheckConstraint("notice_period IS NULL OR notice_period IN ('1d', '7d', '1m')", name=op.f("ck_applications_notice_period_valid")),
        sa.CheckConstraint(
            "status IN ('draft', 'guarantee_issued', 'awaiting_contract', "
            "'contract_signed', 'active', 'expired', 'terminated')",
            name=op.f("ck_applications_status_valid"),
        ),
        sa.CheckConstraint(
            "(type = 'initial_registration' AND planned_client_name IS NOT NULL) "
            "OR (type = 'address_change' AND client_id IS NOT NULL "
            "    AND term_months IS NOT NULL AND notice_period IS NOT NULL)",
            name=op.f("ck_applications_type_invariant"),
        ),
    )
    op.create_index("ix_applications_status_expires_at", "applications", ["status", "expires_at"])
    op.create_index("ix_applications_provider_address", "applications", ["provider_id", "address_id"])
    op.create_index("ix_applications_client_id", "applications", ["client_id"])
    op.create_index("ix_applications_parent_application_id", "applications", ["parent_application_id"])
    op.create_index("ix_applications_type_status", "applications", ["type", "status"])

    # ----- contracts -----
    op.create_table(
        "contracts",
        _uuid_pk(),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("contract_date", sa.Date(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("price_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_total_in_words", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
        sa.UniqueConstraint("application_id", name=op.f("uq_contracts_application_id")),
        sa.UniqueConstraint("number", name=op.f("uq_contracts_number")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_contracts_application_id_applications")),
        sa.CheckConstraint("end_date > start_date", name=op.f("ck_contracts_end_after_start")),
        sa.CheckConstraint("price_total > 0", name=op.f("ck_contracts_price_positive")),
    )
    op.create_index("ix_contracts_contract_date", "contracts", [sa.text("contract_date DESC")])

    # ----- guarantee_letters -----
    op.create_table(
        "guarantee_letters",
        _uuid_pk(),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("number", sa.Text(), nullable=False),
        sa.Column("letter_date", sa.Date(), nullable=False),
        sa.Column("egrn_extract_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guarantee_letters")),
        sa.UniqueConstraint("number", name=op.f("uq_guarantee_letters_number")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="RESTRICT", name=op.f("fk_guarantee_letters_application_id_applications")),
        sa.ForeignKeyConstraint(["egrn_extract_id"], ["egrn_extracts.id"], name=op.f("fk_guarantee_letters_egrn_extract_id_egrn_extracts")),
        sa.CheckConstraint("variant IN ('initial', 'full')", name=op.f("ck_guarantee_letters_variant_valid")),
    )
    op.create_index("ix_guarantee_letters_application_id", "guarantee_letters", ["application_id"])

    # ----- document_templates -----
    op.create_table(
        "document_templates",
        _uuid_pk(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_sha256", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("uploaded_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_templates")),
        sa.UniqueConstraint("kind", "version", name=op.f("uq_document_templates_kind")),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], name=op.f("fk_document_templates_uploaded_by_users")),
        sa.CheckConstraint("kind IN ('contract', 'guarantee_initial', 'guarantee_full')", name=op.f("ck_document_templates_kind_valid")),
        sa.CheckConstraint("version > 0", name=op.f("ck_document_templates_version_positive")),
    )
    op.create_index(
        "uniq_active_template_per_kind", "document_templates", ["kind"],
        unique=True, postgresql_where=sa.text("is_active = true"),
    )

    # ----- generated_documents -----
    op.create_table(
        "generated_documents",
        _uuid_pk(),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True)),
        sa.Column("egrn_extract_id", postgresql.UUID(as_uuid=True)),
        sa.Column("docx_url", sa.Text()),
        sa.Column("pdf_url", sa.Text()),
        sa.Column("zip_url", sa.Text()),
        sa.Column("generated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generated_documents")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE", name=op.f("fk_generated_documents_application_id_applications")),
        sa.ForeignKeyConstraint(["template_id"], ["document_templates.id"], name=op.f("fk_generated_documents_template_id_document_templates")),
        sa.ForeignKeyConstraint(["egrn_extract_id"], ["egrn_extracts.id"], name=op.f("fk_generated_documents_egrn_extract_id_egrn_extracts")),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], name=op.f("fk_generated_documents_generated_by_users")),
        sa.CheckConstraint("kind IN ('contract', 'guarantee', 'package_zip')", name=op.f("ck_generated_documents_kind_valid")),
    )
    op.create_index("ix_generated_documents_application_id", "generated_documents", ["application_id", sa.text("generated_at DESC")])

    # ----- триггеры обновления updated_at -----
    op.execute("""
    CREATE OR REPLACE FUNCTION trigger_set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    for tbl in ("users", "providers", "addresses", "clients", "applications"):
        op.execute(
            f"CREATE TRIGGER set_{tbl}_updated_at BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();"
        )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS trigger_set_updated_at() CASCADE")
    for table in (
        "generated_documents",
        "document_templates",
        "guarantee_letters",
        "contracts",
        "applications",
        "clients",
        "egrn_extracts",
        "addresses",
        "providers",
        "users",
    ):
        op.drop_table(table)
