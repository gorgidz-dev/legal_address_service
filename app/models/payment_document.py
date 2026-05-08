from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class PaymentDocument(UUIDPKMixin, Base):
    __tablename__ = "payment_documents"
    __table_args__ = (
        Index("ix_payment_documents_client_id", "client_id", "created_at"),
    )

    client_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    file_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("stored_files.id"), nullable=False)
    payment_date: Mapped[Optional[date]] = mapped_column(Date)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
