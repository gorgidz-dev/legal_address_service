from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class IncomingWebhook(UUIDPKMixin, Base):
    """Audit log + idempotency store for webhook callbacks from external systems.

    `(provider, external_id)` is unique — replaying the same event is a no-op.
    """

    __tablename__ = "incoming_webhooks"
    __table_args__ = (
        Index(
            "ix_incoming_webhooks_provider_external_id",
            "provider",
            "external_id",
            unique=True,
        ),
    )

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[Optional[str]] = mapped_column(Text)
    raw_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
