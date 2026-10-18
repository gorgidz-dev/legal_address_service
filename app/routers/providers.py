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
from app.schemas.owner_payout import ProviderPayoutSettingsRead, ProviderPayoutSettingsUpdate
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
    "/{provider_id}/payout-settings",
    response_model=ProviderPayoutSettingsRead,
    summary="Процент комиссии и реквизиты собственника (выплаты, агентский чек)",
    dependencies=[Depends(require_admin)],
)
async def set_provider_payout_settings(
    provider_id: UUID,
    payload: ProviderPayoutSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProviderPayoutSettingsRead:
    """Меняются только переданные поля. Процент применяется к новым оплатам: в уже
    заведённой выплате он — снимок на момент оплаты (app/services/owner_payouts.py).
    Реквизиты в выплату попадают снимком в момент отметки «выплачено».
    """
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собственник не найден")
    for field in payload.model_fields_set:
        setattr(provider, field, getattr(payload, field))
    if provider.kpp and provider.inn and len(provider.inn) == 12:
        # КПП бывает только у организаций (ИНН из 10 цифр).
        await db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "КПП бывает только у организаций — у ИП и физлица (ИНН из 12 цифр) оставьте поле пустым.",
        )
    await db.commit()
    return ProviderPayoutSettingsRead(
        provider_id=provider.id,
        commission_percent=provider.commission_percent,
        effective_percent=resolve_commission_percent(provider),
        bank_name=provider.bank_name,
        settlement_account=provider.settlement_account,
        corr_account=provider.corr_account,
        bik=provider.bik,
        full_name=provider.full_name,
        inn=provider.inn,
        kpp=provider.kpp,
        phone=provider.phone,
        receipt_vat=provider.receipt_vat,
    )
