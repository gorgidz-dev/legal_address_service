"""Admin-API: каталог доп.услуг на конкретном адресе.

Каталог `kind` фиксированный (enum AddressServiceKind), но за конкретный
адрес и цену отвечают админ/собственник. Сейчас доступ закрыт за `require_admin`
— редактирование владельцем выделим в owner-роут отдельно при необходимости.

URL под `/api/v1/admin/addresses/{address_id}/services` — короткий REST:
- GET    — все записи (active + inactive), отсортированы по kind;
- PUT    — upsert по (address_id, kind): тело {price, is_active};
- DELETE — полностью убрать запись (тогда услуга недоступна на адресе).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.enums import ADDRESS_SERVICE_KIND_VALUES, AddressServiceKind
from app.models.address import Address
from app.models.address_service import AddressService


router = APIRouter(
    prefix="/admin/addresses/{address_id}/services",
    tags=["admin", "address-services"],
    dependencies=[Depends(require_admin)],
)


class AddressServiceAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    price: Decimal
    is_active: bool


class AddressServiceUpsert(BaseModel):
    price: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
    is_active: bool = True


async def _load_address(db: AsyncSession, address_id: UUID) -> Address:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    return address


def _validate_kind(kind: str) -> AddressServiceKind:
    try:
        return AddressServiceKind(kind)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Недопустимый kind. Доступно: {', '.join(ADDRESS_SERVICE_KIND_VALUES)}",
        ) from e


@router.get("", response_model=list[AddressServiceAdminRead])
async def list_services(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[AddressService]:
    await _load_address(db, address_id)
    result = await db.execute(
        select(AddressService)
        .where(AddressService.address_id == address_id)
        .order_by(AddressService.kind)
    )
    return list(result.scalars().all())


@router.put("/{kind}", response_model=AddressServiceAdminRead)
async def upsert_service(
    address_id: UUID,
    kind: str,
    payload: AddressServiceUpsert,
    db: AsyncSession = Depends(get_db),
) -> AddressService:
    await _load_address(db, address_id)
    valid_kind = _validate_kind(kind)

    existing = (
        await db.execute(
            select(AddressService).where(
                AddressService.address_id == address_id,
                AddressService.kind == valid_kind.value,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        record = AddressService(
            address_id=address_id,
            kind=valid_kind.value,
            price=payload.price,
            is_active=payload.is_active,
        )
        db.add(record)
    else:
        existing.price = payload.price
        existing.is_active = payload.is_active
        record = existing

    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{kind}")
async def delete_service(
    address_id: UUID,
    kind: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    valid_kind = _validate_kind(kind)
    existing = (
        await db.execute(
            select(AddressService).where(
                AddressService.address_id == address_id,
                AddressService.kind == valid_kind.value,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
