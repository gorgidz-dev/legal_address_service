from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.database import get_db
from app.models.address import Address
from app.models.provider import Provider
from app.schemas.address import AddressCreate, AddressRead
from app.services.dadata_address import geocode
from app.services.fns_office import resolve_fns_office_for_address

router = APIRouter(prefix="/addresses", tags=["addresses"], dependencies=[Depends(require_staff)])


@router.get(
    "",
    response_model=list[AddressRead],
    summary="Список помещений (опционально по собственнику)",
)
async def list_addresses(
    provider_id: Optional[UUID] = None,
    available_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> list[Address]:
    stmt = select(Address).order_by(Address.full_address)
    if provider_id is not None:
        stmt = stmt.where(Address.provider_id == provider_id)
    if available_only:
        stmt = stmt.where(Address.is_available.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=AddressRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать помещение",
)
async def create_address(
    payload: AddressCreate,
    db: AsyncSession = Depends(get_db),
) -> Address:
    # Дружелюбная проверка существования собственника — без этого FK выдаст 409 без подсказки.
    provider = await db.get(Provider, payload.provider_id)
    if provider is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Provider {payload.provider_id} не найден",
        )

    address = Address(**payload.model_dump())

    # Гео-привязка через DaData: регион/город/ИФНС из текста адреса.
    # Опционально — сбой DaData не блокирует создание адреса.
    try:
        office = await resolve_fns_office_for_address(db, address.full_address)
        if office is not None:
            address.fns_office_id = office.id
    except Exception:  # noqa: BLE001
        pass

    # Координаты для карты через DaData (geo_lat/geo_lon). Опционально —
    # сбой/нет токена не блокирует создание (координаты проставит бэкфилл).
    try:
        point = await geocode(address.full_address)
        if point is not None:
            address.latitude = Decimal(str(round(point[0], 6)))
            address.longitude = Decimal(str(round(point[1], 6)))
    except Exception:  # noqa: BLE001
        pass

    db.add(address)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logging.getLogger(__name__).warning("IntegrityError on address create: %s", e.orig)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Нарушено ограничение целостности данных",
        ) from e
    await db.refresh(address)
    return address


@router.get("/{address_id}", response_model=AddressRead)
async def get_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Address:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Address {address_id} не найден")
    return address
