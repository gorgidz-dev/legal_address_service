from __future__ import annotations

"""Платёжные схемы: эквайринг Т-Банка / CDEK Pay (физлица), счёт (юрлица)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contacts import OptionalEmail, OptionalPhone
from app.enums import PaymentAttachmentKind, PaymentPayerType, PaymentStatus


class PaymentInitiateRequest(BaseModel):
    application_id: UUID
    payer_type: Literal[PaymentPayerType.INDIVIDUAL] = PaymentPayerType.INDIVIDUAL
    # Allow client to override contact details (otherwise — берётся из заявки).
    user_phone: OptionalPhone = None
    user_email: OptionalEmail = None


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    provider: str
    payer_type: PaymentPayerType
    status: PaymentStatus
    amount_kopeks: int
    currency: str
    pay_for: str
    qr_link: Optional[str] = None
    qr_image_base64: Optional[str] = None
    cdek_access_key: Optional[str] = None
    cdek_order_id: Optional[int] = None
    cdek_payment_id: Optional[int] = None
    # Т-Банк: ссылка на платёжную форму (карта, СБП, T-Pay) — фронт и приложение
    # открывают её, QR-код рисует сам банк.
    payment_url: Optional[str] = None
    provider_payment_id: Optional[str] = None
    provider_status: Optional[str] = None
    refunded_kopeks: int = 0
    # Закрывающий чек «полный расчёт» (54-ФЗ): NULL | due | sending | sent |
    # failed | unknown — см. app/services/tbank_receipts.py. Сам Receipt (с
    # e-mail покупателя) в API не отдаём.
    closing_receipt_status: Optional[str] = None
    closing_receipt_at: Optional[datetime] = None
    closing_receipt_error: Optional[str] = None
    expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("refunded_kopeks", mode="before")
    @classmethod
    def _refunded_default(cls, value: Optional[int]) -> int:
        # Умолчание колонки ставит база при вставке; у ещё не сохранённого
        # объекта атрибут None, а в API должно быть число.
        return 0 if value is None else value


class PaymentRefundRequest(BaseModel):
    """Только админ. value_refund_kopeks по умолчанию — полная сумма."""
    value_refund_kopeks: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(min_length=2, max_length=500)


class ClosingReceiptAction(BaseModel):
    """Только админ. send — (повторно) отправить закрывающий чек; mark_sent —
    чек найден в ЛК Т-Бизнеса (после обрыва связи), повторять не нужно."""
    action: Literal["send", "mark_sent"]


class PaymentManualConfirmRequest(BaseModel):
    """Для provider=manual_invoice: админ подтверждает поступление оплаты вручную."""
    comment: Optional[str] = Field(default=None, max_length=500)


class PaymentRejectRequest(BaseModel):
    """Для provider=manual_invoice: админ помечает платёж как не пришедший."""
    reason: str = Field(min_length=2, max_length=500)


class PaymentAttachmentRead(BaseModel):
    """Документ платежа (счёт или платёжное поручение) для выдачи в API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    kind: PaymentAttachmentKind
    original_filename: str
    size_bytes: int
    uploaded_by: Optional[UUID] = None
    created_at: datetime
    download_url: str


class PaymentReceiptConfirm(BaseModel):
    """Собственник подтверждает поступление средств по счёту."""

    comment: Optional[str] = Field(default=None, max_length=500)


class CdekCallbackPaymentBody(BaseModel):
    """Body, который CDEK Pay шлёт на наш webhook."""

    payment: dict[str, Any]
    signature: str = Field(min_length=64, max_length=128)


class CdekCallbackRefundBody(CdekCallbackPaymentBody):
    """Refund callback имеет ту же оболочку (только refund_amount вместо pay_amount)."""
