"""Outbound webhook delivery.

Pipeline:
1. `dispatch_event(db, event, payload)` enqueues a WebhookDelivery row for every
   active subscription that listens to that event (or `*`).
2. `deliver_pending(db, limit)` picks up rows whose `scheduled_for <= now()` and
   POSTs them with an HMAC-SHA256 signature in `X-Webhook-Signature`.
3. On failure: increment attempts, push `scheduled_for` into the future with
   exponential backoff, mark `dead` after MAX_ATTEMPTS.

Receivers verify the signature, treat the `X-Webhook-Delivery-Id` header as the
idempotency key. Payload schema: { "id", "event", "occurred_at", "data" }.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
INITIAL_BACKOFF = timedelta(seconds=60)
MAX_BACKOFF = timedelta(hours=4)
WILDCARD_EVENT = "*"
DELIVERY_TIMEOUT_SECONDS = 10.0
SIGNATURE_HEADER = "X-Webhook-Signature"
DELIVERY_ID_HEADER = "X-Webhook-Delivery-Id"
EVENT_HEADER = "X-Webhook-Event"


class UnsafeWebhookUrl(ValueError):
    """URL подписки указывает на приватную/служебную сеть (SSRF-риск)."""


def assert_safe_webhook_url(url: str) -> None:
    """Отклоняет URL, ведущие внутрь инфраструктуры (SSRF-защита).

    Проверяет схему (только http/https) и что ВСЕ адреса, в которые резолвится
    хост, публичные — не loopback/private/link-local/reserved/multicast. Вызывать
    при создании/смене URL подписки. resolve-time проверка не закрывает
    DNS-rebinding на 100%, но отсекает очевидные `http://169.254.169.254`,
    `http://localhost`, `http://10.x` и т.п.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebhookUrl("URL webhook должен использовать http или https")
    host = parsed.hostname
    if not host:
        raise UnsafeWebhookUrl("URL webhook без хоста")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeWebhookUrl(f"Не удалось разрешить хост webhook: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeWebhookUrl(
                f"URL webhook указывает на приватный/служебный адрес ({ip})"
            )


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 over the raw JSON body. Returns hex digest prefixed with sha256=."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, header_value: str | None) -> bool:
    if not header_value:
        return False
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, header_value)


def compute_backoff(attempts: int) -> timedelta:
    """Exponential: 60s, 2m, 4m, 8m, 16m… capped at MAX_BACKOFF."""
    seconds = INITIAL_BACKOFF.total_seconds() * (2 ** max(0, attempts - 1))
    delta = timedelta(seconds=seconds)
    return delta if delta <= MAX_BACKOFF else MAX_BACKOFF


async def dispatch_event(
    db: AsyncSession,
    *,
    event: str,
    data: dict[str, Any],
) -> list[WebhookDelivery]:
    """Enqueue delivery rows for every active subscription that listens to `event`."""
    now = utcnow()
    result = await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.is_active.is_(True),
            (WebhookSubscription.events.contains([event]))
            | (WebhookSubscription.events.contains([WILDCARD_EVENT])),
        )
    )
    subscriptions = list(result.scalars().all())
    deliveries: list[WebhookDelivery] = []
    for sub in subscriptions:
        delivery = WebhookDelivery(
            subscription_id=sub.id,
            event=event,
            payload=data,
            status="pending",
            attempts=0,
            scheduled_for=now,
            created_at=now,
        )
        db.add(delivery)
        deliveries.append(delivery)
    if deliveries:
        await db.flush()
    return deliveries


def _envelope(*, delivery_id: UUID, event: str, occurred_at: datetime, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(delivery_id),
        "event": event,
        "occurred_at": occurred_at.isoformat(),
        "data": data,
    }


@dataclass(frozen=True)
class DeliveryAttemptResult:
    delivery_id: UUID
    succeeded: bool
    status_code: int | None
    error: str | None


async def _post_delivery(
    *,
    url: str,
    secret: str,
    delivery: WebhookDelivery,
    client: httpx.AsyncClient | None = None,
) -> DeliveryAttemptResult:
    envelope = _envelope(
        delivery_id=delivery.id,
        event=delivery.event,
        occurred_at=delivery.created_at,
        data=delivery.payload,
    )
    body = json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: sign_payload(secret, body),
        DELIVERY_ID_HEADER: str(delivery.id),
        EVENT_HEADER: delivery.event,
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS)
    try:
        response = await client.post(url, content=body, headers=headers)
        succeeded = 200 <= response.status_code < 300
        return DeliveryAttemptResult(
            delivery_id=delivery.id,
            succeeded=succeeded,
            status_code=response.status_code,
            error=None if succeeded else f"HTTP {response.status_code}",
        )
    except httpx.HTTPError as e:
        return DeliveryAttemptResult(
            delivery_id=delivery.id,
            succeeded=False,
            status_code=None,
            error=str(e)[:500],
        )
    finally:
        if owns_client:
            await client.aclose()


async def _claim_pending(
    db: AsyncSession,
    *,
    limit: int,
) -> list[tuple[WebhookDelivery, WebhookSubscription]]:
    """Atomically mark pending deliveries 'in_progress' and return them with subscription rows."""
    now = utcnow()
    candidates_stmt = (
        select(WebhookDelivery.id)
        .where(
            WebhookDelivery.status == "pending",
            WebhookDelivery.scheduled_for <= now,
        )
        .order_by(WebhookDelivery.scheduled_for)
        .limit(limit)
    )
    candidates = (await db.execute(candidates_stmt)).scalars().all()
    if not candidates:
        return []

    claim_stmt = (
        update(WebhookDelivery)
        .where(
            WebhookDelivery.id.in_(candidates),
            WebhookDelivery.status == "pending",
        )
        .values(status="in_progress")
        .returning(WebhookDelivery.id)
    )
    claimed_ids = [row.id for row in (await db.execute(claim_stmt)).all()]
    if not claimed_ids:
        return []

    rows_stmt = (
        select(WebhookDelivery, WebhookSubscription)
        .join(WebhookSubscription, WebhookSubscription.id == WebhookDelivery.subscription_id)
        .where(WebhookDelivery.id.in_(claimed_ids))
    )
    return [(d, s) for d, s in (await db.execute(rows_stmt)).all()]


async def deliver_pending(
    db: AsyncSession,
    *,
    limit: int = 20,
    client: httpx.AsyncClient | None = None,
) -> list[DeliveryAttemptResult]:
    """Pick up to `limit` pending deliveries and POST them. Returns per-delivery results."""
    rows = await _claim_pending(db, limit=limit)
    results: list[DeliveryAttemptResult] = []
    now = utcnow()
    for delivery, subscription in rows:
        result = await _post_delivery(
            url=subscription.url,
            secret=subscription.secret,
            delivery=delivery,
            client=client,
        )
        delivery.attempts += 1
        delivery.last_status_code = result.status_code
        delivery.last_error = result.error
        if result.succeeded:
            delivery.status = "sent"
            delivery.delivered_at = now
        elif delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "dead"
            log.warning(
                "Webhook delivery %s gave up after %d attempts to %s",
                delivery.id,
                delivery.attempts,
                subscription.url,
            )
        else:
            delivery.status = "pending"
            delivery.scheduled_for = now + compute_backoff(delivery.attempts)
        results.append(result)
    await db.commit()
    return results
