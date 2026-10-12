"""Выплата собственнику по заявке, оплаченной через площадку.

Жизненный цикл и правила — app/services/owner_payouts.py; схема — миграция 0036.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class OwnerPayout(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "owner_payouts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_registration', 'due', 'paid', 'cancelled')",
            name="status_valid",
        ),
        CheckConstraint("gross_kopeks > 0", name="gross_positive"),
        CheckConstraint(
            "(commission_percent IS NULL AND commission_kopeks IS NULL AND payout_kopeks IS NULL)"
            " OR (commission_percent >= 0 AND commission_percent < 100"
            " AND commission_kopeks >= 0 AND payout_kopeks > 0"
            " AND commission_kopeks + payout_kopeks = gross_kopeks)",
            name="split_consistent",
        ),
        CheckConstraint(
            "status IN ('awaiting_registration', 'cancelled') OR payout_kopeks IS NOT NULL",
            name="amount_known",
        ),
        CheckConstraint(
            "status <> 'paid' OR (paid_on IS NOT NULL AND paid_at IS NOT NULL"
            " AND bank_reference IS NOT NULL)",
            name="paid_complete",
        ),
        CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name="cancel_reason"),
        Index("ux_owner_payouts_payment_id", "payment_id", unique=True),
        Index(
            "ux_owner_payouts_one_active_per_application",
            "application_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
        Index("ix_owner_payouts_status", "status", "created_at"),
        Index("ix_owner_payouts_provider", "provider_id", "status"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("applications.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False
    )
    provider_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, server_default="'awaiting_registration'", nullable=False
    )
    # Что заплатил клиент, и как это делится: снимок на момент оплаты.
    gross_kopeks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commission_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    commission_kopeks: Mapped[Optional[int]] = mapped_column(BigInteger)
    payout_kopeks: Mapped[Optional[int]] = mapped_column(BigInteger)

    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # paid_on — дата платёжного поручения (её вводит админ); paid_at — когда отметили.
    paid_on: Mapped[Optional[date]] = mapped_column(Date)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    bank_reference: Mapped[Optional[str]] = mapped_column(Text)
    # Реквизиты получателя на момент выплаты: у собственника они могут смениться.
    payee: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB(none_as_null=True))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
