"""Схемы выплат собственникам (app/routers/owner_payouts.py)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.validators import BIK, CorrAccount, INNLegal, SettlementAccount

PayoutStatus = Literal["awaiting_registration", "due", "paid", "cancelled"]


class RegistrationLookupRequest(BaseModel):
    """Сверка регистрации. Смена адреса — ИНН берётся из заявки (поля не нужны);
    первичная — поиск по `name` (по умолчанию название из заявки) или проверка
    выбранного кандидата по `inn`."""
    inn: Optional[INNLegal] = None
    name: Optional[str] = Field(default=None, max_length=300)


class RegistrationConfirmRequest(BaseModel):
    # Смена адреса — можно не передавать (ИНН из заявки, другой не примем);
    # первичная — ИНН выбранного кандидата.
    inn: Optional[INNLegal] = None
    # Подсказки «название/адрес не совпали» — эвристика; если админ сверил
    # вручную, он подтверждает с этой отметкой (она пишется в снимок).
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
    expected_name: Optional[str] = None
    name_matches: Optional[bool] = None
    warnings: list[str] = []


class RegistrationLookupRead(BaseModel):
    mode: Literal["inn", "name"]
    query: Optional[str] = None
    candidates: list[RegistrationCheckRead] = []
    # Смена адреса — ИНН компании из заявки; первичная — название из заявки.
    expected_inn: Optional[str] = None
    expected_name: Optional[str] = None


class PayoutMarkPaidRequest(BaseModel):
    paid_on: date
    bank_reference: str = Field(min_length=1, max_length=100)
    comment: Optional[str] = Field(default=None, max_length=1000)


class PayoutCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ProviderPayoutSettingsUpdate(BaseModel):
    """Настройки выплат собственника. Меняются только переданные поля.

    commission_percent: null — своего процента нет, действует общий из настроек.
    Реквизиты меняет только админ: собственник, сам меняющий счёт для выплат, —
    готовый способ увести деньги при взломе его входа.
    """
    commission_percent: Optional[Decimal] = Field(default=None, ge=0, lt=100, decimal_places=2)
    bank_name: Optional[str] = Field(default=None, max_length=300)
    settlement_account: Optional[SettlementAccount] = None
    corr_account: Optional[CorrAccount] = None
    bik: Optional[BIK] = None


class ProviderPayoutSettingsRead(BaseModel):
    provider_id: UUID
    commission_percent: Optional[Decimal] = None
    # Что реально применится к новым оплатам: свой процент или общий.
    effective_percent: Optional[Decimal] = None
    bank_name: Optional[str] = None
    settlement_account: Optional[str] = None
    corr_account: Optional[str] = None
    bik: Optional[str] = None


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
    # Дата регистрации из расписки ИФНС — раньше неё сверять ЕГРЮЛ бесполезно.
    registration_expected_on: Optional[date] = None
    registration_check: Optional[dict[str, Any]] = None
    # ИНН, который можно подставить в проверку: сообщённый клиентом, а для смены
    # адреса — ИНН самой компании из заявки.
    suggested_inn: Optional[str] = None
    # Почему двигать выплату сейчас нельзя (пусто — можно).
    blockers: list[str] = []


class RegistrationConfirmResult(BaseModel):
    """Регистрация подтверждена. payout — выплата собственнику, если деньги
    принимала площадка; null — выплаты по заявке нет (счёт собственника)."""
    application_id: UUID
    registration_confirmed_at: datetime
    payout: Optional[AdminPayoutRead] = None

