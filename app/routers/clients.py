from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.client import Client
from app.schemas.client import ClientRead, ClientUpdate, DaDataLookupResponse
from app.services.dadata import (
    DaDataError,
    DaDataNotConfigured,
    get_dadata_service,
)
from app.validators import INNLegal

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get(
    "/lookup-by-inn",
    response_model=DaDataLookupResponse,
    summary="Поиск ЮЛ в ЕГРЮЛ через DaData",
    description=(
        "Возвращает данные клиента по ИНН (10 знаков), включая блокеры — "
        "статус ликвидации, дисквалификация подписанта, признак филиала. "
        "Используется на форме создания заявки address_change.\n\n"
        "Кэш: повторные запросы с тем же ИНН в течение 24 часов "
        "не дёргают DaData."
    ),
    responses={
        404: {"description": "ИНН не найден в ЕГРЮЛ"},
        502: {"description": "DaData недоступна"},
        503: {"description": "DaData не настроена (DADATA_TOKEN отсутствует)"},
    },
)
async def lookup_by_inn(inn: INNLegal) -> DaDataLookupResponse:
    try:
        service = get_dadata_service()
    except DaDataNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    try:
        result = await service.lookup(inn)
    except DaDataError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"ИНН {inn} не найден в ЕГРЮЛ",
        )
    return result


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")
    return client


@router.patch(
    "/{client_id}",
    response_model=ClientRead,
    summary="Дозаполнить вручную те поля, которых нет в DaData (банк, e-mail и т.п.)",
)
async def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, key, value)
    await db.commit()
    await db.refresh(client)
    return client
