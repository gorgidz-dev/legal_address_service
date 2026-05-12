"""Admin CRUD for webhook subscriptions + delivery log."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription
from app.schemas.webhook import (
    WebhookDeliveryRead,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreateResult,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
    generate_secret,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/subscriptions", response_model=list[WebhookSubscriptionRead])
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[WebhookSubscription]:
    result = await db.execute(
        select(WebhookSubscription).order_by(WebhookSubscription.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/subscriptions",
    response_model=WebhookSubscriptionCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    payload: WebhookSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> WebhookSubscriptionCreateResult:
    secret = payload.secret or generate_secret()
    sub = WebhookSubscription(
        url=str(payload.url),
        description=payload.description,
        events=payload.events,
        secret=secret,
        is_active=True,
        created_by=admin.id,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return WebhookSubscriptionCreateResult(
        id=sub.id,
        url=sub.url,
        description=sub.description,
        events=sub.events,
        is_active=sub.is_active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        secret=secret,
    )


@router.patch("/subscriptions/{subscription_id}", response_model=WebhookSubscriptionCreateResult)
async def update_subscription(
    subscription_id: UUID,
    payload: WebhookSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> WebhookSubscriptionCreateResult:
    sub = await db.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Подписка не найдена")

    if payload.url is not None:
        sub.url = str(payload.url)
    if payload.description is not None:
        sub.description = payload.description
    if payload.events is not None:
        sub.events = payload.events
    if payload.is_active is not None:
        sub.is_active = payload.is_active
    new_secret: str | None = None
    if payload.rotate_secret:
        new_secret = generate_secret()
        sub.secret = new_secret

    await db.commit()
    await db.refresh(sub)
    return WebhookSubscriptionCreateResult(
        id=sub.id,
        url=sub.url,
        description=sub.description,
        events=sub.events,
        is_active=sub.is_active,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
        # Secret only echoed if it was just rotated. Otherwise empty string sentinel.
        secret=new_secret or "",
    )


@router.delete(
    "/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> Response:
    sub = await db.get(WebhookSubscription, subscription_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Подписка не найдена")
    await db.delete(sub)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/subscriptions/{subscription_id}/deliveries",
    response_model=list[WebhookDeliveryRead],
)
async def list_deliveries(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[WebhookDelivery]:
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.subscription_id == subscription_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())
