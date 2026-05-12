"""Admin CRUD for webhook subscriptions + delivery log + inbound provider hooks."""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models.incoming_webhook import IncomingWebhook
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription
from app.routers.payments import (
    handle_cdek_pay_payment_callback,
    handle_cdek_pay_refund_callback,
)
from app.schemas.webhook import (
    WebhookDeliveryRead,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreateResult,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
    generate_secret,
)
from app.services.cdek_pay import (
    CdekPayNotConfigured,
    get_cdek_pay_service,
    verify_callback_signature,
)
from app.services.webhooks import SIGNATURE_HEADER, verify_signature

log = logging.getLogger(__name__)

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


def _extract_external_id(body: dict[str, Any]) -> str | None:
    """Pick whatever field the provider uses for event-id idempotency."""
    for key in ("id", "event_id", "delivery_id", "notification_id"):
        value = body.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    return None


@router.post(
    "/payments/{provider}",
    summary="Inbound payment webhook (HMAC-verified, idempotent)",
)
async def inbound_payment_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receive a payment-status callback from an external provider.

    Verification:
    - HMAC-SHA256 over the raw body with `PAYMENT_WEBHOOK_SECRET`, sent in
      `X-Webhook-Signature: sha256=<hex>`.

    Idempotency:
    - The provider's event id (`id` / `event_id` / `delivery_id` / `notification_id`)
      stored on `(provider, external_id)` unique index. Replays return 200 with
      `replayed: true`.

    This endpoint only persists the event; downstream payment-application logic
    is wired in by the "payments" feature (separate work item).
    """
    if not settings.payment_webhook_secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "webhook_not_configured",
                "message": "Payment webhook secret is not configured on the server",
            },
        )

    raw = await request.body()
    signature = request.headers.get(SIGNATURE_HEADER)
    if not verify_signature(settings.payment_webhook_secret, raw, signature):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "bad_signature",
                "message": "Подпись запроса не совпала",
            },
        )

    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_json", "message": f"Invalid JSON: {e}"},
        ) from e
    if not isinstance(body, dict):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_payload", "message": "Корневой элемент должен быть объектом"},
        )

    external_id = _extract_external_id(body)
    if not external_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "missing_event_id",
                "message": "Нет поля id/event_id/delivery_id/notification_id для идемпотентности",
            },
        )

    record = IncomingWebhook(
        provider=provider,
        external_id=external_id,
        event_type=body.get("event") or body.get("type"),
        raw_body=body,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        log.info("Replayed payment webhook %s/%s — already stored", provider, external_id)
        return {"received": True, "replayed": True}

    return {"received": True, "replayed": False}


# ============================================================
# CDEK Pay callbacks (own signature scheme — see app/services/cdek_pay.py)
# ============================================================


async def _read_cdek_body(request: Request) -> tuple[bytes, dict[str, Any]]:
    raw = await request.body()
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_json", "message": f"Invalid JSON: {e}"},
        ) from e
    if not isinstance(body, dict):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_payload", "message": "Корневой элемент должен быть объектом"},
        )
    return raw, body


async def _store_idempotent(
    db: AsyncSession,
    *,
    provider: str,
    external_id: str,
    event_type: str,
    body: dict[str, Any],
) -> bool:
    """Returns True if newly stored, False if it was a replay (already in DB)."""
    record = IncomingWebhook(
        provider=provider,
        external_id=external_id,
        event_type=event_type,
        raw_body=body,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        log.info("Replayed CDEK webhook %s/%s — already stored", provider, external_id)
        return False
    return True


@router.post(
    "/cdek_pay/payment",
    summary="CDEK Pay — успешный платёж (callback)",
)
async def cdek_pay_payment_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        service = get_cdek_pay_service()
    except CdekPayNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    _raw, body = await _read_cdek_body(request)
    payment_section = body.get("payment") or {}
    signature = body.get("signature") or ""
    if not isinstance(payment_section, dict) or not signature:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ожидаются поля payment (object) и signature (string)",
        )
    if not verify_callback_signature(payment_section, signature, service.secret_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Подпись не совпала")

    external_id = str(payment_section.get("id") or "")
    if not external_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Нет payment.id")

    stored = await _store_idempotent(
        db,
        provider="cdek_pay",
        external_id=external_id,
        event_type="payment_success",
        body=body,
    )
    if not stored:
        return {"received": True, "replayed": True}

    await handle_cdek_pay_payment_callback(db=db, body=body)
    return {"received": True, "replayed": False}


@router.post(
    "/cdek_pay/refund",
    summary="CDEK Pay — успешный возврат (callback)",
)
async def cdek_pay_refund_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        service = get_cdek_pay_service()
    except CdekPayNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    _raw, body = await _read_cdek_body(request)
    payment_section = body.get("payment") or {}
    signature = body.get("signature") or ""
    if not isinstance(payment_section, dict) or not signature:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ожидаются поля payment (object) и signature (string)",
        )
    if not verify_callback_signature(payment_section, signature, service.secret_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Подпись не совпала")

    external_id = f"refund:{payment_section.get('id', '')}"
    if external_id == "refund:":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Нет payment.id")

    stored = await _store_idempotent(
        db,
        provider="cdek_pay",
        external_id=external_id,
        event_type="refund_success",
        body=body,
    )
    if not stored:
        return {"received": True, "replayed": True}

    await handle_cdek_pay_refund_callback(db=db, body=body)
    return {"received": True, "replayed": False}
