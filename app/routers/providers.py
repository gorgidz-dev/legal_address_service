from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_staff
from app.database import get_db
from app.models.provider import Provider
from app.schemas.owner_payout import ProviderCommissionRead, ProviderCommissionUpdate
from app.schemas.provider import ProviderCreate, ProviderRead
from app.services.owner_payouts import resolve_commission_percent

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


@router.patch(
    "/{provider_id}/commission",
    response_model=ProviderCommissionRead,
    summary="Процент комиссии площадки с собственника",
    dependencies=[Depends(require_admin)],
)
async def set_provider_commission(
    provider_id: UUID,
    payload: ProviderCommissionUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProviderCommissionRead:
    """Свой процент собственника; null — действует общий из настроек.

    Применяется к новым оплатам: в уже заведённой выплате процент — снимок на
    момент оплаты (app/services/owner_payouts.py).
    """
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собственник не найден")
    provider.commission_percent = payload.commission_percent
    await db.commit()
    return ProviderCommissionRead(
        provider_id=provider.id,
        commission_percent=provider.commission_percent,
        effective_percent=resolve_commission_percent(provider),
    )

