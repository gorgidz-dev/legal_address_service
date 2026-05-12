from __future__ import annotations

"""Workflow публикации адресов: submit (owner) → publish/reject (admin) → archive."""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin, utcnow
from app.database import get_db
from app.enums import AddressPublicationStatus, UserRole
from app.models.address import Address
from app.models.user import User
from app.schemas.address import AddressModerationReject, AddressRead

router = APIRouter(tags=["address-moderation"])


async def _load_address(db: AsyncSession, address_id: UUID) -> Address:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    return address


def _assert_owner_or_admin(user: User, address: Address) -> None:
    if user.role == UserRole.ADMIN.value:
        return
    if user.role == UserRole.OWNER.value and user.provider_id == address.provider_id:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Действие доступно администратору или собственнику этого адреса",
    )


@router.post("/addresses/{address_id}/submit", response_model=AddressRead)
async def submit_address_for_moderation(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Address:
    address = await _load_address(db, address_id)
    _assert_owner_or_admin(user, address)
    current = AddressPublicationStatus(address.publication_status)
    if current not in (AddressPublicationStatus.DRAFT, AddressPublicationStatus.REJECTED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Из статуса {current.value} нельзя отправить на модерацию",
        )
    address.publication_status = AddressPublicationStatus.MODERATION.value
    address.moderation_comment = None
    address.moderated_by = None
    address.moderated_at = None
    await db.commit()
    await db.refresh(address)
    return address


@router.post("/addresses/{address_id}/archive", response_model=AddressRead)
async def archive_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Address:
    address = await _load_address(db, address_id)
    _assert_owner_or_admin(user, address)
    current = AddressPublicationStatus(address.publication_status)
    if current == AddressPublicationStatus.ARCHIVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Адрес уже архивирован")
    address.publication_status = AddressPublicationStatus.ARCHIVED.value
    address.moderated_by = user.id
    address.moderated_at = utcnow()
    await db.commit()
    await db.refresh(address)
    return address


admin_router = APIRouter(
    prefix="/admin",
    tags=["address-moderation"],
    dependencies=[Depends(require_admin)],
)


@admin_router.get("/addresses", response_model=list[AddressRead])
async def admin_list_addresses_for_moderation(
    publication_status: Optional[AddressPublicationStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[Address]:
    stmt = select(Address).order_by(Address.updated_at.desc())
    if publication_status is not None:
        stmt = stmt.where(Address.publication_status == publication_status.value)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@admin_router.post("/addresses/{address_id}/publish", response_model=AddressRead)
async def publish_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Address:
    address = await _load_address(db, address_id)
    current = AddressPublicationStatus(address.publication_status)
    if current != AddressPublicationStatus.MODERATION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Опубликовать можно только из moderation, текущий статус: {current.value}",
        )
    now = utcnow()
    address.publication_status = AddressPublicationStatus.PUBLISHED.value
    address.moderation_comment = None
    address.moderated_by = admin.id
    address.moderated_at = now
    address.published_at = now
    await db.commit()
    await db.refresh(address)
    return address


@admin_router.post("/addresses/{address_id}/reject", response_model=AddressRead)
async def reject_address(
    address_id: UUID,
    payload: AddressModerationReject,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Address:
    address = await _load_address(db, address_id)
    current = AddressPublicationStatus(address.publication_status)
    if current != AddressPublicationStatus.MODERATION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Отклонить можно только из moderation, текущий статус: {current.value}",
        )
    address.publication_status = AddressPublicationStatus.REJECTED.value
    address.moderation_comment = payload.moderation_comment
    address.moderated_by = admin.id
    address.moderated_at = utcnow()
    await db.commit()
    await db.refresh(address)
    return address
