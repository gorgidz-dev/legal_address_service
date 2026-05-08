from __future__ import annotations

"""
Pydantic-схемы для заявки.

Заявка имеет два типа, форма ввода у них РАЗНАЯ — поэтому используется
discriminated union по полю `type`. Это даёт чистую OpenAPI-схему,
понятную автогенератору TypeScript-клиента.
"""
from datetime import date, datetime
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import ApplicationStatus, ApplicationType, NoticePeriod
from app.validators import INNLegal


# ============================================================
# Создание заявки — два варианта по типу
# ============================================================

class _ApplicationCreateBase(BaseModel):
    provider_id: UUID
    address_id: UUID
    contract_city: Optional[str] = Field(
        default=None,
        description="Город заключения договора. Если не указан — берётся из адреса собственника.",
    )
    fns_number: Optional[int] = Field(
        default=None, ge=1, le=9999,
        description="Номер ИФНС для шапки гарантийки. Prefill из address.fns_number.",
    )
    fns_city: Optional[str] = None


class ApplicationCreateInitial(_ApplicationCreateBase):
    """Заявка на первичную регистрацию ЮЛ — компания ещё не создана."""

    type: Literal[ApplicationType.INITIAL_REGISTRATION] = ApplicationType.INITIAL_REGISTRATION
    planned_client_name: str = Field(
        min_length=1, max_length=200,
        description="Название будущего ЮЛ без ОПФ, напр. «Альфа»",
        examples=["Альфа"],
    )


class ApplicationCreateAddressChange(_ApplicationCreateBase):
    """Заявка на смену адреса существующего ЮЛ."""

    type: Literal[ApplicationType.ADDRESS_CHANGE] = ApplicationType.ADDRESS_CHANGE
    client_inn: INNLegal = Field(
        description="ИНН клиента — реквизиты подтянутся из DaData при создании заявки.",
    )
    term_months: Literal[6, 11]
    notice_period: NoticePeriod
    has_correspondence_service: bool = False


ApplicationCreate = Annotated[
    Union[ApplicationCreateInitial, ApplicationCreateAddressChange],
    Field(discriminator="type"),
]


# ============================================================
# Чтение заявки
# ============================================================

class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: ApplicationType
    status: ApplicationStatus

    provider_id: UUID
    address_id: UUID

    client_id: Optional[UUID] = None
    planned_client_name: Optional[str] = None

    term_months: Optional[int] = None
    notice_period: Optional[NoticePeriod] = None
    has_correspondence_service: bool
    contract_city: Optional[str] = None

    fns_number: Optional[int] = None
    fns_city: Optional[str] = None

    expires_at: Optional[date] = None
    parent_application_id: Optional[UUID] = None

    created_at: datetime
    updated_at: datetime


# ============================================================
# Повышение initial-заявки в договорную после регистрации ЮЛ
# ============================================================

class PromoteToContractRequest(BaseModel):
    """
    Когда клиент возвращается с ИНН после первичной регистрации, эту команду
    вызывает менеджер. Создаёт новую заявку (`address_change`), привязанную
    к исходной через `parent_application_id`, и сразу запускает генерацию договора.
    """

    client_inn: INNLegal
    term_months: Literal[6, 11]
    notice_period: NoticePeriod
    has_correspondence_service: bool = False
    contract_city: Optional[str] = None
