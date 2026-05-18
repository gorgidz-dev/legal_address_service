from __future__ import annotations

"""Платёжные схемы (CDEK Pay SBP-flow для физлиц)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    expires_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PaymentRefundRequest(BaseModel):
    """Только админ. value_refund_kopeks по умолчанию — полная сумма."""
    value_refund_kopeks: Optional[int] = Field(default=None, gt=0)
    reason: str = Field(min_length=2, max_length=500)


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
