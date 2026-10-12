from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
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
        Index(
            "ix_applications_registration_expected_on",
            "registration_expected_on",
            postgresql_where=text(
                "registration_expected_on IS NOT NULL AND registration_confirmed_at IS NULL"
            ),
        ),
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
    # Внутренний срок текущего этапа: к этому моменту должен отработать
    # собственник или оператор. NULL = в этом статусе ждать нечего (заявка
    # завершена, отменена или мяч на стороне клиента). Клиенту не отдаётся —
    # см. services/application_sla.py.
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    parent_application_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id"),
    )

    created_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"),
    )

    # Подтверждение регистрации компании клиента по адресу — условие выплаты
    # собственнику (app/services/owner_payouts.py). ИНН сообщает клиент или
    # вводит админ; registration_check — снимок сверки с ЕГРЮЛ (DaData) на
    # момент подтверждения.
    registration_inn: Mapped[Optional[str]] = mapped_column(Text)
    registration_inn_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    registration_check: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True))
    registration_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    registration_confirmed_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
    )
    # Статус-трекер (этап 6): клиент сам подаёт документы в ИФНС и загружает
    # расписку о приёме (stored_files, kind = ifns_receipt) с датой предстоящей
    # регистрации — от неё строится прогноз и напоминание «пора сверить».
    registration_expected_on: Mapped[Optional[date]] = mapped_column(Date)
    ifns_receipt_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Что разобрано из PDF расписки (app/services/ifns_receipt.py): название,
    # ИНН/ОГРН, номер, даты. Название — для сверки первичной регистрации.
    ifns_receipt_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True))
