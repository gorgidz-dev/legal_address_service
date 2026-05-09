from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Application(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "type IN ('initial_registration', 'address_change')",
            name="type_valid",
        ),
        CheckConstraint(
            "status IN ("
            "'draft', 'guarantee_issued', 'awaiting_contract', 'contract_signed', "
            "'active', 'expired', 'terminated', 'awaiting_payment', 'paid', "
            "'admin_review', 'needs_client_fix', 'assigned_to_owner', "
            "'accepted_by_owner', 'rejected_by_owner', 'documents_preparing', "
            "'documents_uploaded', 'documents_review', 'documents_revision', "
            "'ready_for_client', 'completed', 'cancelled', 'dispute', "
            "'refund_pending', 'refunded')",
            name="status_valid",
        ),
        CheckConstraint(
            "term_months IS NULL OR term_months IN (6, 11)",
            name="term_months_valid",
        ),
        CheckConstraint(
            "notice_period IS NULL OR notice_period IN ('1d', '7d', '1m')",
            name="notice_period_valid",
        ),
        # Главный инвариант: у первички — planned_client_name; у address_change — client_id и срок.
        CheckConstraint(
            "(type = 'initial_registration' AND planned_client_name IS NOT NULL) "
            "OR (type = 'address_change' AND client_id IS NOT NULL "
            "    AND term_months IS NOT NULL AND notice_period IS NOT NULL)",
            name="type_invariant",
        ),
        Index("ix_applications_status_expires_at", "status", "expires_at"),
        Index("ix_applications_provider_address", "provider_id", "address_id"),
        Index("ix_applications_client_id", "client_id"),
        Index("ix_applications_parent_application_id", "parent_application_id"),
        Index("ix_applications_type_status", "type", "status"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)

    provider_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("providers.id"), nullable=False,
    )
    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("addresses.id"), nullable=False,
    )

    client_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("clients.id"),
    )
    planned_client_name: Mapped[Optional[str]] = mapped_column(Text)
    company_name: Mapped[Optional[str]] = mapped_column(Text)
    contact_name: Mapped[Optional[str]] = mapped_column(Text)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text)
    contact_email: Mapped[Optional[str]] = mapped_column(Text)

    term_months: Mapped[Optional[int]] = mapped_column(SmallInteger)
    has_correspondence_service: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False,
    )
    notice_period: Mapped[Optional[str]] = mapped_column(Text)
    contract_city: Mapped[Optional[str]] = mapped_column(Text)

    fns_number: Mapped[Optional[int]] = mapped_column(SmallInteger)
    fns_city: Mapped[Optional[str]] = mapped_column(Text)

    status: Mapped[str] = mapped_column(Text, server_default="'draft'", nullable=False)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)

    parent_application_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id"),
    )

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"),
    )
