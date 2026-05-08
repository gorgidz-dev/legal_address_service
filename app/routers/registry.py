from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.address import Address
from app.models.application import Application
from app.models.client import Client
from app.models.contract import Contract
from app.models.provider import Provider
from app.schemas.registry import ActiveClientRegistryItem, renewal_state

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get(
    "/active-clients",
    response_model=list[ActiveClientRegistryItem],
    summary="Реестр действующих клиентов и сроков пролонгации",
)
async def active_clients_registry(
    due_within_days: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ActiveClientRegistryItem]:
    today = date.today()
    stmt = (
        select(Application, Contract, Client, Provider, Address)
        .join(Contract, Contract.application_id == Application.id)
        .join(Client, Client.id == Application.client_id)
        .join(Provider, Provider.id == Application.provider_id)
        .join(Address, Address.id == Application.address_id)
        .where(
            Application.type == "address_change",
            Application.status.in_(["contract_signed", "active"]),
        )
        .order_by(Contract.end_date.asc(), Client.short_name.asc())
    )
    result = await db.execute(stmt)
    rows = []
    for application, contract, client, provider, address in result.all():
        days_until_renewal = (contract.end_date - today).days
        if due_within_days is not None and days_until_renewal > due_within_days:
            continue
        rows.append(
            ActiveClientRegistryItem(
                application_id=application.id,
                contract_id=contract.id,
                client_id=client.id,
                company_name=application.company_name or client.short_name,
                client_inn=client.inn,
                contact_name=application.contact_name,
                contact_phone=application.contact_phone,
                contact_email=application.contact_email,
                provider_name=provider.short_name,
                address_full=address.full_address,
                contract_number=contract.number,
                contract_date=contract.contract_date,
                start_date=contract.start_date,
                end_date=contract.end_date,
                renewal_date=contract.end_date,
                term_months=application.term_months or 0,
                days_until_renewal=days_until_renewal,
                price_total=contract.price_total,
                renewal_status=renewal_state(contract.end_date, today=today),
            )
        )
    return rows
