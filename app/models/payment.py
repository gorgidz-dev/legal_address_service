from __future__ import annotations

"""Платёж за заявку: эквайринг Т-Банка или CDEK Pay (физлица), счёт (юрлица)."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
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
        CheckConstraint(
            "provider IN ('cdek_pay', 'manual_invoice', 'tbank')", name="provider_valid"
        ),
        CheckConstraint("amount_kopeks > 0", name="amount_positive"),
        # Вернуть больше, чем заплатили, нельзя.
        CheckConstraint(
            "refunded_kopeks >= 0 AND refunded_kopeks <= amount_kopeks",
            name="refunded_non_negative",
        ),
        Index("ix_payments_application_id", "application_id"),
        Index("ix_payments_status_created", "status", "created_at"),
        Index("ix_payments_cdek_access_key", "cdek_access_key", unique=True),
        Index(
            "ix_payments_cdek_payment_id",
            "cdek_payment_id",
            unique=True,
            postgresql_where="cdek_payment_id IS NOT NULL",
        ),
        Index(
            "ux_payments_provider_payment_id",
            "provider",
            "provider_payment_id",
            unique=True,
            postgresql_where="provider_payment_id IS NOT NULL",
        ),
        # Один незавершённый платёж на заявку. Без этого два одновременных
        # нажатия «Оплатить» создавали два платежа — и клиент мог оплатить дважды.
        Index(
            "ux_payments_one_active_per_application",
            "application_id",
            unique=True,
            postgresql_where="status IN ('pending', 'awaiting_user')",
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

    # Общие для провайдеров с внешним идентификатором (Т-Банк). PaymentId банка —
    # строкой: как число он теряет точность в JS.
    provider_payment_id: Mapped[Optional[str]] = mapped_column(Text)
    # Последний сырой статус банка (NEW, CONFIRMED, REFUNDED…) — для поддержки и сверки.
    provider_status: Mapped[Optional[str]] = mapped_column(Text)
    # Терминал, на котором создан платёж. После смены DEMO на боевой старые
    # платежи новому терминалу неизвестны — спрашивать о них банк бессмысленно.
    provider_account: Mapped[Optional[str]] = mapped_column(Text)
    payment_url: Mapped[Optional[str]] = mapped_column(Text)
    # Сколько возвращено — только то, что банк ПОДТВЕРДИЛ.
    refunded_kopeks: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    # Счётчик наших попыток возврата. Растёт только при НОВОЙ попытке — после
    # окончательного отказа банка; повтор незавершённой попытки идёт тем же ключом.
    refund_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # ExternalRequestId нашего текущего возврата (refund:<id>:<попытка>). NULL —
    # нашего возврата «в пути» нет; при refund_requested это значит, что возврат
    # запустили мимо нас (из ЛК Т-Бизнеса). Повтор тем же ключом банк не
    # исполнит дважды — поэтому незавершённую попытку безопасно отправить снова.
    refund_key: Mapped[Optional[str]] = mapped_column(Text)
    # Когда последний раз спрашивали статус у банка (GetState) — чтобы опрос
    # страницы оплаты раз в 3 секунды не превращался в запрос к банку раз в 3 секунды.
    provider_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    last_callback_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    initiated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
