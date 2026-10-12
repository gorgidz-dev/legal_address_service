"""Схемы выплат собственникам (app/routers/owner_payouts.py)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.validators import INNLegal

PayoutStatus = Literal["awaiting_registration", "due", "paid", "cancelled"]


class RegistrationInnRequest(BaseModel):
    """ИНН компании, зарегистрированной по адресу заявки."""
    inn: INNLegal


class RegistrationConfirmRequest(BaseModel):
    inn: INNLegal
    # Подсказка «адрес не совпал» — эвристика; если админ сверил адрес вручную и
    # это тот же адрес, он подтверждает с этой отметкой (она пишется в снимок).
    accept_address_mismatch: bool = False


class RegistrationCheckRead(BaseModel):
    inn: str
    found: bool
    full_name: Optional[str] = None
    ogrn: Optional[str] = None
    registration_date: Optional[date] = None
    egrul_status: Optional[str] = None
    legal_address: Optional[str] = None
    our_address: Optional[str] = None
    address_matches: Optional[bool] = None
    warnings: list[str] = []


class ApplicationRegistrationRead(BaseModel):
    application_id: UUID
    registration_inn: Optional[str] = None
    registration_inn_submitted_at: Optional[datetime] = None
    registration_confirmed_at: Optional[datetime] = None


class PayoutMarkPaidRequest(BaseModel):
    paid_on: date
    bank_reference: str = Field(min_length=1, max_length=100)
    comment: Optional[str] = Field(default=None, max_length=1000)


class PayoutCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ProviderCommissionUpdate(BaseModel):
    """NULL — у собственника нет своего процента, действует общий из настроек."""
    commission_percent: Optional[Decimal] = Field(default=None, ge=0, lt=100, decimal_places=2)


class ProviderCommissionRead(BaseModel):
    provider_id: UUID
    commission_percent: Optional[Decimal] = None
    # Что реально применится к новым оплатам: свой процент или общий.
    effective_percent: Optional[Decimal] = None


class PayoutPayee(BaseModel):
    full_name: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    bank_name: Optional[str] = None
    settlement_account: Optional[str] = None
    corr_account: Optional[str] = None
    bik: Optional[str] = None


class OwnerPayoutRead(BaseModel):
    """Выплата глазами собственника: только своя и без данных площадки."""
    id: UUID
    status: PayoutStatus
    application_id: UUID
    application_label: str
    address: Optional[str] = None
    gross_kopeks: int
    commission_percent: Optional[Decimal] = None
    commission_kopeks: Optional[int] = None
    payout_kopeks: Optional[int] = None
    due_at: Optional[datetime] = None
    paid_on: Optional[date] = None
    bank_reference: Optional[str] = None
    cancel_reason: Optional[str] = None
    created_at: datetime


class AdminPayoutRead(OwnerPayoutRead):
    application_type: str
    application_status: str
    provider_id: UUID
    provider_name: str
    payment_id: UUID
    payment_status: str
    paid_at: Optional[datetime] = None
    comment: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    # Реквизиты: после выплаты — снимок на момент выплаты, до — текущие у собственника.
    payee: PayoutPayee
    registration_inn: Optional[str] = None
    registration_inn_submitted_at: Optional[datetime] = None
    registration_confirmed_at: Optional[datetime] = None
    registration_check: Optional[dict[str, Any]] = None
    # ИНН, который можно подставить в проверку: сообщённый клиентом, а для смены
    # адреса — ИНН самой компании из заявки.
    suggested_inn: Optional[str] = None
    # Почему двигать выплату сейчас нельзя (пусто — можно).
    blockers: list[str] = []
