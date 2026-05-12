from __future__ import annotations

"""Платёж за заявку через CDEK Pay (СБП для физлиц, в будущем — другие)."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class Payment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','awaiting_user','succeeded','failed',"
            "'expired','cancelled','refund_requested','refunded')",
            name="status_valid",
        ),
        CheckConstraint("payer_type IN ('individual','juridical')", name="payer_type_valid"),
        CheckConstraint("provider IN ('cdek_pay')", name="provider_valid"),
        CheckConstraint("amount_kopeks > 0", name="amount_positive"),
        Index("ix_payments_application_id", "application_id"),
        Index("ix_payments_status_created", "status", "created_at"),
        Index("ix_payments_cdek_access_key", "cdek_access_key", unique=True),
        Index(
            "ix_payments_cdek_payment_id",
            "cdek_payment_id",
            unique=True,
            postgresql_where="cdek_payment_id IS NOT NULL",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # "cdek_pay"
    payer_type: Mapped[str] = mapped_column(Text, nullable=False)  # individual|juridical
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="'pending'")

    amount_kopeks: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)  # TST|RUR
    pay_for: Mapped[str] = mapped_column(Text, nullable=False)

    # CDEK-specific identifiers (filled after sbp_qrs response)
    cdek_access_key: Mapped[Optional[str]] = mapped_column(Text)
    cdek_order_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    cdek_payment_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    qr_link: Mapped[Optional[str]] = mapped_column(Text)
    qr_image_base64: Mapped[Optional[str]] = mapped_column(Text)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    last_callback_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    initiated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
