from __future__ import annotations

"""Pydantic-схемы для клиента (ЮЛ, заполняется через DaData)."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import EgrulStatus
from app.validators import (
    BIK,
    INNLegal,
    KPP,
    OGRN,
    CorrAccount,
    SettlementAccount,
)


class DaDataLookupResponse(BaseModel):
    """Ответ нашего эндпоинта-обёртки над DaData по ИНН — для preview перед созданием."""

    inn: INNLegal
    kpp: Optional[KPP]
    ogrn: Optional[OGRN]
    full_name: str
    short_name: str
    legal_address: Optional[str]
    kladr_id: Optional[str]
    signatory_name: Optional[str]
    signatory_position: Optional[str]
    okved_main_code: Optional[str]
    okved_main_name: Optional[str]
    egrul_status: EgrulStatus

    class Blockers(BaseModel):
        liquidating_or_liquidated: bool
        bankrupt: bool
        signatory_disqualified: bool
        is_branch: bool

    blockers: Blockers


class ClientUpdate(BaseModel):
    """Поля, которые менеджер вводит сам — DaData их не отдаёт."""

    bank_name: Optional[str] = None
    settlement_account: Optional[SettlementAccount] = None
    corr_account: Optional[CorrAccount] = None
    bik: Optional[BIK] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    signatory_basis: Optional[str] = Field(
        default=None,
        description="«Устава» по умолчанию; при доверенности — её реквизиты",
    )


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    inn: INNLegal
    kpp: Optional[KPP]
    ogrn: Optional[OGRN]
    ogrn_date: Optional[date]
    okpo: Optional[str]
    okved_main_code: Optional[str]
    okved_main_name: Optional[str]

    full_name: str
    short_name: str
    legal_address: Optional[str]
    kladr_id: Optional[str]

    signatory_name: Optional[str]
    signatory_position: Optional[str]
    signatory_basis: str
    signatory_initials: Optional[str]

    bank_name: Optional[str]
    settlement_account: Optional[SettlementAccount]
    corr_account: Optional[CorrAccount]
    bik: Optional[BIK]
    email: Optional[EmailStr]
    phone: Optional[str]

    egrul_status: Optional[EgrulStatus]
    last_dadata_refresh_at: Optional[datetime]

    created_at: datetime
    updated_at: datetime
