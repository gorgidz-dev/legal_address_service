"""Web Push: подписка/отписка устройства + публичный VAPID-ключ.

- `GET /api/v1/push/public-key` — клиент берёт ключ перед subscribe (открыт).
- `POST /api/v1/push/subscribe` — сохраняем эндпоинт и ключи устройства.
- `DELETE /api/v1/push/subscribe?endpoint=...` — отписка (на logout / unsubscribe).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.web_push import is_push_enabled

router = APIRouter(prefix="/push", tags=["push"])


class PushKeyRead(BaseModel):
    public_key: str
    enabled: bool


class PushSubscribePayload(BaseModel):
    endpoint: str = Field(min_length=10)
    p256dh: str = Field(min_length=10)
    auth: str = Field(min_length=5)


@router.get("/public-key", response_model=PushKeyRead)
async def push_public_key() -> PushKeyRead:
    return PushKeyRead(public_key=settings.vapid_public_key, enabled=is_push_enabled())


@router.post("/subscribe")
async def push_subscribe(
    payload: PushSubscribePayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not is_push_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web Push выключен")
    # Replace by endpoint, чтобы один и тот же браузер не плодил дубли.
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.user_agent = request.headers.get("user-agent")
    else:
        record = PushSubscription(
            user_id=user.id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh,
            auth=payload.auth,
            user_agent=request.headers.get("user-agent"),
        )
        db.add(record)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Не удалось сохранить подписку") from e
    return {"ok": True}


@router.delete("/subscribe")
async def push_unsubscribe(
    endpoint: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    record = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.endpoint == endpoint,
                PushSubscription.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if record is not None:
        await db.delete(record)
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
