"""Резолв справочника ИФНС: upsert fns_offices + привязка к адресу."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fns_office import FnsOffice
from app.services.dadata_address import suggest_address

log = logging.getLogger(__name__)


async def get_or_create_fns_office(
    db: AsyncSession,
    *,
    code: str,
    name: str,
    short_number: Optional[int],
    region: str,
    city: str,
) -> FnsOffice:
    """Возвращает FnsOffice по коду; создаёт, если такого ещё нет."""
    existing = (
        await db.execute(select(FnsOffice).where(FnsOffice.code == code))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    office = FnsOffice(
        code=code,
        name=name,
        short_number=short_number,
        region=region,
        city=city,
    )
    db.add(office)
    await db.flush()
    return office


async def resolve_fns_office_for_address(
    db: AsyncSession, full_address: str
) -> Optional[FnsOffice]:
    """Разбирает адрес через DaData и возвращает соответствующую ИФНС.

    None — если DaData не настроена / не нашла / не вернула код ИФНС.
    Создание адреса от результата не зависит — гео-привязка опциональна.
    """
    result = await suggest_address(full_address)
    if result is None or not result.fns_code:
        return None
    return await get_or_create_fns_office(
        db,
        code=result.fns_code,
        name=result.fns_name or f"ИФНС {result.fns_code}",
        short_number=result.fns_short_number,
        region=result.region,
        city=result.city,
    )
