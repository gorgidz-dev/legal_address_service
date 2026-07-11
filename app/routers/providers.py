from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.database import get_db
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderRead

router = APIRouter(prefix="/providers", tags=["providers"], dependencies=[Depends(require_staff)])


@router.get("", response_model=list[ProviderRead], summary="Список собственников")
async def list_providers(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
) -> list[Provider]:
    stmt = select(Provider).order_by(Provider.code)
    if active_only:
        stmt = stmt.where(Provider.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать собственника",
)
async def create_provider(
    payload: ProviderCreate,
    db: AsyncSession = Depends(get_db),
) -> Provider:
    provider = Provider(**payload.model_dump(exclude_unset=False))
    db.add(provider)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        logging.getLogger(__name__).warning("IntegrityError on provider create: %s", e.orig)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Нарушено ограничение целостности данных",
        ) from e
    await db.refresh(provider)
    return provider


@router.get("/{provider_id}", response_model=ProviderRead)
async def get_provider(
    provider_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Provider:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider {provider_id} не найден")
    return provider
