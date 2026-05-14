"""Web Push: отправка через pywebpush.

Если VAPID-ключи не настроены — отправка скипается без ошибок (push-feature
просто отключён, остальные нотификации продолжают работать).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger("web_push")


def is_push_enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_pem)


def _send_one(subscription_info: dict, payload: dict) -> tuple[bool, int | None]:
    """Синхронный вызов pywebpush. Возвращает (ok, status_code_if_failed)."""
    try:
        from pywebpush import WebPushException, webpush

        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_pem,
            vapid_claims={"sub": settings.vapid_subject},
            timeout=10,
        )
        return True, None
    except WebPushException as e:  # type: ignore[name-defined]  # noqa: F821 (lazy import)
        status_code = getattr(e.response, "status_code", None)
        return False, status_code
    except Exception:  # noqa: BLE001
        logger.warning("webpush failed", exc_info=True)
        return False, None


async def send_push_to_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    body: str,
    url: str | None = None,
    tag: str | None = None,
) -> int:
    """Шлёт push на все подписки пользователя. Возвращает количество ОК.

    410/404 от провайдера → подписка протухла, удаляем из БД.
    """
    if not is_push_enabled():
        return 0

    subs = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
    ).scalars().all()
    if not subs:
        return 0

    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url
    if tag:
        payload["tag"] = tag

    sent = 0
    to_delete: list[PushSubscription] = []
    for sub in subs:
        info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        ok, status_code = await asyncio.to_thread(_send_one, info, payload)
        if ok:
            sent += 1
        elif status_code in (404, 410):
            to_delete.append(sub)

    for sub in to_delete:
        await db.delete(sub)
    if to_delete:
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
    return sent


async def send_push_to_users(
    db: AsyncSession,
    *,
    user_ids: Iterable[UUID],
    title: str,
    body: str,
    url: str | None = None,
    tag: str | None = None,
) -> int:
    total = 0
    for uid in user_ids:
        total += await send_push_to_user(db, user_id=uid, title=title, body=body, url=url, tag=tag)
    return total
