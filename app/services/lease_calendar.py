"""Сборка календаря аренды для кабинетов клиента и собственника.

Запрос один, отличается только тем, по какому полю отсекается своё: клиент
видит договоры по своим заявкам, собственник — по своим адресам. Держать это
в сервисе, а не в двух роутерах, — чтобы условие «действующий договор» было
записано один раз: разъедься оно, и одна из сторон увидела бы у себя аренду,
которой у другой уже нет.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationStatus, ApplicationType
from app.models.address import Address
from app.models.application import Application
from app.models.contract import Contract
from app.models.provider import Provider
from app.schemas.lease_calendar import LeaseCalendarItem
from app.schemas.registry import renewal_state

#: Договор считается действующим в этих статусах заявки — те же, что в реестре
#: оператора (`registry.active_clients_registry`).
ACTIVE_STATUSES = (
    ApplicationStatus.CONTRACT_SIGNED.value,
    ApplicationStatus.ACTIVE.value,
)


def _base_query():
    return (
        select(Application, Contract, Address, Provider)
        .join(Contract, Contract.application_id == Application.id)
        .join(Address, Address.id == Application.address_id)
        .join(Provider, Provider.id == Application.provider_id)
        .where(
            Application.type == ApplicationType.ADDRESS_CHANGE.value,
            Application.status.in_(ACTIVE_STATUSES),
        )
        .order_by(Contract.end_date.asc())
    )


async def lease_calendar_for_client(
    *,
    db: AsyncSession,
    user_id: UUID,
    today: date | None = None,
) -> list[LeaseCalendarItem]:
    """Аренды клиента. Контрагент в карточке — собственник."""
    today = today or date.today()
    result = await db.execute(_base_query().where(Application.created_by == user_id))
    return [
        _item(
            application=application,
            contract=contract,
            address=address,
            counterparty=provider.short_name,
            today=today,
        )
        for application, contract, address, provider in result.all()
    ]


async def lease_calendar_for_owner(
    *,
    db: AsyncSession,
    provider_id: UUID,
    today: date | None = None,
) -> list[LeaseCalendarItem]:
    """Аренды собственника. Контрагент — компания клиента."""
    today = today or date.today()
    result = await db.execute(_base_query().where(Application.provider_id == provider_id))
    return [
        _item(
            application=application,
            contract=contract,
            address=address,
            counterparty=application.company_name or "Клиент",
            today=today,
        )
        for application, contract, address, _provider in result.all()
    ]


def _item(
    *,
    application: Application,
    contract: Contract,
    address: Address,
    counterparty: str,
    today: date,
) -> LeaseCalendarItem:
    return LeaseCalendarItem(
        application_id=application.id,
        contract_id=contract.id,
        contract_number=contract.number,
        address_full=address.full_address,
        room_number=address.room_number,
        counterparty=counterparty,
        start_date=contract.start_date,
        end_date=contract.end_date,
        days_until_renewal=(contract.end_date - today).days,
        renewal_status=renewal_state(contract.end_date, today=today),
        price_total=contract.price_total,
    )
