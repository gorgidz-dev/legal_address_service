from __future__ import annotations

"""Pydantic-схемы для собственника помещения (Исполнитель). По умолчанию ИП."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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

    phone: Optional[str] = None


class ProviderCreate(ProviderBase):
    pass


class ProviderRead(ProviderBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
