"""Документы платежа: счёт от собственника и платёжное поручение от клиента.

Используется в manual_invoice-флоу (оплата юр.лицом по безналу):
- собственник грузит счёт (kind=invoice);
- клиент грузит платёжку с отметкой банка (kind=payment_order) — действие
  «я оплатил»;
- собственник, увидев платёжку, подтверждает поступление средств.

Привязка строго к Payment — без пересечения с legacy-моделью PaymentDocument
(та ключена на client_id и обслуживает другой, внутренний staff-флоу).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.stored_file import StoredFile


class PaymentAttachment(UUIDPKMixin, Base):
    __tablename__ = "payment_attachments"

    payment_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # invoice | payment_order — см. PaymentAttachmentKind.
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("stored_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    file: Mapped["StoredFile"] = relationship()
