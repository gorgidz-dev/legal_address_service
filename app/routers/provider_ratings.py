"""Внутренняя оценка собственников — ручка оператора.

Отдельный роутер под /admin, и это не косметика: оценка внутренняя, и её
недоступность клиенту должна следовать из зависимости роутера, а не из
внимательности того, кто добавит следующую ручку.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.database import get_db
from app.models.provider import Provider
from app.schemas.provider_rating import MetricRead, ProviderRatingRead
from app.services.provider_rating import ratings_for_all_providers

router = APIRouter(
    prefix="/admin/provider-ratings",
    tags=["provider-ratings"],
    dependencies=[Depends(require_staff)],
)


@router.get(
    "",
    response_model=list[ProviderRatingRead],
    summary="Внутренняя оценка работы собственников",
)
async def provider_ratings(db: AsyncSession = Depends(get_db)) -> list[ProviderRatingRead]:
    ratings = await ratings_for_all_providers(db=db)
    providers = await db.execute(select(Provider.id, Provider.short_name))
    names = {row[0]: row[1] for row in providers.all()}

    rows = [
        ProviderRatingRead(
            provider_id=provider_id,
            provider_name=names.get(provider_id, "Собственник"),
            response=MetricRead(**vars(rating.response)),
            cards=MetricRead(**vars(rating.cards)),
            documents=MetricRead(**vars(rating.documents)),
            score=rating.score,
        )
        for provider_id, rating in ratings.items()
    ]
    # Сначала те, у кого хуже; собственники без данных — в конец, они не
    # «плохие», про них просто нечего сказать.
    rows.sort(key=lambda row: (row.score is None, row.score if row.score is not None else 0))
    return rows
