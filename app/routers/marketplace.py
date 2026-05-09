from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import AddressPublicationStatus, OwnerConnectionRequestStatus
from app.models.address import Address
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.schemas.marketplace import (
    ProviderConnectionRequestCreate,
    ProviderConnectionRequestRead,
    PublicAddressRead,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def public_address_from_row(
    *,
    address: Address,
    provider: Provider,
    term_months: Literal[6, 11] = 11,
) -> PublicAddressRead:
    selected_price: Decimal = address.price_6m if term_months == 6 else address.price_11m
    return PublicAddressRead(
        id=address.id,
        provider_id=address.provider_id,
        provider_name=provider.short_name,
        full_address=address.full_address,
        room_number=address.room_number,
        price_6m=address.price_6m,
        price_11m=address.price_11m,
        selected_price=selected_price,
        correspondence_price=address.correspondence_price,
        fns_number=address.fns_number,
        fns_city=address.fns_city,
        is_available=address.is_available,
        publication_status=address.publication_status,
        created_at=address.created_at,
        updated_at=address.updated_at,
    )


@router.get("/addresses", response_model=list[PublicAddressRead])
async def public_addresses(
    city: Annotated[Optional[str], Query(max_length=120)] = None,
    fns_number: Annotated[Optional[int], Query(ge=1, le=9999)] = None,
    term_months: Annotated[int, Query()] = 11,
    correspondence: Annotated[Optional[bool], Query()] = None,
    db: AsyncSession = Depends(get_db),
) -> list[PublicAddressRead]:
    if term_months not in (6, 11):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="term_months must be 6 or 11")

    stmt = (
        select(Address, Provider)
        .join(Provider, Provider.id == Address.provider_id)
        .where(
            Provider.is_active.is_(True),
            Address.is_available.is_(True),
            Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
        )
        .order_by(Address.full_address)
    )
    if city:
        stmt = stmt.where(Address.full_address.ilike(f"%{city.strip()}%"))
    if fns_number is not None:
        stmt = stmt.where(Address.fns_number == fns_number)
    if correspondence is True:
        stmt = stmt.where(Address.correspondence_price.is_not(None))

    result = await db.execute(stmt)
    return [
        public_address_from_row(address=address, provider=provider, term_months=6 if term_months == 6 else 11)
        for address, provider in result.all()
    ]


@router.post(
    "/provider-requests",
    response_model=ProviderConnectionRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_request(
    payload: ProviderConnectionRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> ProviderConnectionRequest:
    request = ProviderConnectionRequest(
        **payload.model_dump(),
        status=OwnerConnectionRequestStatus.NEW.value,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request
