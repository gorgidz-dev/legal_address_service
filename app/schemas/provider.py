from __future__ import annotations

from decimal import Decimal

"""Pydantic-схемы для собственника помещения (Исполнитель). По умолчанию ИП."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.contacts import OptionalPhone
from app.validators import (
    BIK,
    INN,
    KPP,
    OGRNAny,
    CorrAccount,
    SettlementAccount,
)


class ProviderBase(BaseModel):
    code: str = Field(min_length=1, max_length=50, examples=["msk-tverskaya-1"])
    full_name: str = Field(examples=["Индивидуальный предприниматель Иванов Иван Иванович"])
    short_name: str = Field(examples=["ИП Иванов И. И."])

    inn: Optional[INN] = None
    kpp: Optional[KPP] = None
    ogrn: Optional[OGRNAny] = Field(default=None, description="ОГРН (13 знаков) или ОГРНИП (15 знаков)")
    okpo: Optional[str] = None

    legal_address: Optional[str] = None

    signatory_name: Optional[str] = Field(default=None, examples=["Иванов Иван Иванович"])
    signatory_position: Optional[str] = Field(default=None, examples=["Индивидуальный предприниматель"])
    signatory_basis: Optional[str] = Field(default=None, examples=["листа записи ЕГРИП"])
    signatory_initials: Optional[str] = Field(default=None, examples=["Иванов И. И."])

    bank_name: Optional[str] = None
    settlement_account: Optional[SettlementAccount] = None
    corr_account: Optional[CorrAccount] = None
    bik: Optional[BIK] = None

    # On read the phone is shown as-is (legacy unnormalised seed data may exist);
    # ProviderCreate below tightens it to E.164.
    phone: Optional[str] = None


class ProviderCreate(ProviderBase):
    phone: OptionalPhone = None


class ProviderRead(ProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    # Комиссия площадки, % (null — общий процент из настроек). Меняется отдельно:
    # PATCH /providers/{id}/commission, только админ.
    commission_percent: Optional[Decimal] = None
    # Ставка НДС собственника в агентском чеке; null — не указана (оплату не принимаем).
    receipt_vat: Optional[str] = None
    created_at: datetime
    updated_at: datetime
