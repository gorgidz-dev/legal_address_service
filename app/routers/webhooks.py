"""Admin CRUD for webhook subscriptions + delivery log + inbound provider hooks."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, utcnow
from app.config import settings
from app.database import get_db
from app.enums import ApplicationEventKind, NotificationAudience
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
from app.services import tbank_receipts
from app.services.notification_events import create_application_event
from app.services.tbank_acquiring import TBankError, TBankNotConfigured, get_tbank_service
from app.services.tbank_payments import (
    apply_bank_state,
    find_payment_for_notification,
    lock_payment,
    notification_event_id,
    sanitize_for_storage,
)
from app.services.webhooks import (
    SIGNATURE_HEADER,
    UnsafeWebhookUrl,
    assert_safe_webhook_url,
    verify_signature,
)

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
    try:
        await asyncio.to_thread(assert_safe_webhook_url, str(payload.url))
    except UnsafeWebhookUrl as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
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
        try:
            await asyncio.to_thread(assert_safe_webhook_url, str(payload.url))
        except UnsafeWebhookUrl as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
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


async def _read_json_body(request: Request) -> tuple[bytes, dict[str, Any]]:
    raw = await request.body()
    try:
        body = json.loads(raw or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # UnicodeDecodeError — не подкласс JSONDecodeError: без него невалидный
        # UTF-8 в теле давал бы 500 вместо честного 422.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_json", "message": "Тело запроса — не JSON в UTF-8"},
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
    """Insert the idempotency row in the CURRENT transaction (flush, not commit).

    Returns True if newly inserted, False if it was a replay (already committed).
    The caller's handler commits this row together with its side effects in one
    transaction, so a handler failure rolls the idempotency row back too and the
    provider's retry gets processed instead of being swallowed as a fake replay.
    """
    record = IncomingWebhook(
        provider=provider,
        external_id=external_id,
        event_type=event_type,
        raw_body=body,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        log.info("Replayed webhook %s/%s — already stored", provider, external_id)
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

    _raw, body = await _read_json_body(request)
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

    _raw, body = await _read_json_body(request)
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


# ============================================================
# Т-Банк: HTTP-уведомления о статусе платежа
# ============================================================

# Уведомления, которые не про статус нашего платежа: фискализация (Status
# всегда RECEIPT), привязка счёта по СБП и карты. Храним для аудита, платёж
# не трогаем.
_TBANK_SERVICE_NOTIFICATIONS = frozenset({"RECEIPT"})
_TBANK_SERVICE_TYPES = frozenset({"LINKACCOUNT", "LINKCARD"})
_DIGITS_RE = re.compile(r"^[0-9]{1,30}$")


def _ok() -> PlainTextResponse:
    # Ровно «OK» латиницей, без тегов и JSON — иначе банк повторяет уведомление
    # раз в час сутки и раз в день месяц. (На странице тест-кейсов «ОК» набрано
    # кириллицей — оттуда не копировать.)
    return PlainTextResponse("OK")


async def _already_stored(db: AsyncSession, *, provider: str, external_id: str) -> bool:
    stmt = select(IncomingWebhook.id).where(
        IncomingWebhook.provider == provider, IncomingWebhook.external_id == external_id
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


@router.post(
    "/tbank/notification",
    summary="Т-Банк — уведомление о статусе платежа",
    response_class=PlainTextResponse,
)
async def tbank_notification(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Приёмник уведомлений интернет-эквайринга Т-Банка.

    Уведомление — только СИГНАЛ. Его тело для решений не используется: подпись
    Т-Банка склеивает значения без разделителей и не фиксирует набор полей,
    поэтому тело можно подделать при верной подписи (сдвиг границ, лишнее или
    переименованное поле — найдено ревизией). Решение принимается по GetState:
    его ответ приходит по TLS напрямую от банка.

    Подпись и TerminalKey всё равно проверяем — это дешёвый фильтр мусора до
    похода в банк. Порядок: найти платёж → взять блокировку строки → GetState →
    применить → записать уведомление в журнал → commit. Если банк не ответил —
    503: банк повторит уведомление, а журнал не запишется (откат), и повтор
    обработается заново.
    """
    try:
        service = get_tbank_service()
    except TBankNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    _raw, body = await _read_json_body(request)
    if body.get("TerminalKey") != service.terminal_key:
        log.warning("T-Bank notification for foreign terminal %r", body.get("TerminalKey"))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Чужой терминал")
    if not service.verify_notification(body):
        log.warning(
            "T-Bank notification with bad Token: PaymentId=%r Status=%r",
            body.get("PaymentId"), body.get("Status"),
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Подпись не совпала")

    status_value = str(body.get("Status") or "")[:40]
    stored_body = sanitize_for_storage(body)
    event_id = notification_event_id(body)

    async def journal(event_type: str) -> None:
        if await _store_idempotent(
            db, provider="tbank", external_id=event_id, event_type=event_type, body=stored_body
        ):
            await db.commit()

    raw_pid = body.get("PaymentId")
    provider_payment_id = (
        str(raw_pid) if not isinstance(raw_pid, bool) and _DIGITS_RE.match(str(raw_pid)) else None
    )
    order_id = body.get("OrderId")

    if status_value == "RECEIPT":
        # Итог фискализации чека. Касса пробивает чек уже ПОСЛЕ оплаты, и её
        # отказ (не оплачена аренда, кончился ФН, не совпали СНО/ФФД) платёж не
        # останавливает — узнать о нём можно только отсюда. Поэтому ошибку
        # показываем админу. Тело здесь не проверить у банка, но от него
        # зависит лишь оповещение, а не деньги.
        if await _store_idempotent(
            db, provider="tbank", external_id=event_id, event_type="RECEIPT", body=stored_body
        ):
            if body.get("Success") is not True or str(body.get("ErrorCode") or "0") != "0":
                payment = await find_payment_for_notification(
                    db,
                    provider_payment_id=provider_payment_id,
                    order_id=None if order_id is None else str(order_id),
                )
                log.warning(
                    "T-Bank receipt failed: PaymentId=%r ErrorCode=%r", raw_pid, body.get("ErrorCode")
                )
                if payment is not None:
                    reason = str(
                        body.get("ErrorMessage") or body.get("Message") or body.get("Details") or ""
                    )[:300]
                    closing = tbank_receipts.receipt_notification_is_closing(body)
                    if closing and payment.closing_receipt_status == tbank_receipts.SENT:
                        # Банк принял закрывающий чек, а касса его не пробила — открываем
                        # ручной повтор (автоповтор — нет: причину сначала устраняют в ЛК).
                        locked = await lock_payment(db, payment.id)
                        if locked is not None and locked.closing_receipt_status == tbank_receipts.SENT:
                            tbank_receipts.mark_closing_receipt_rejected_by_kassa(
                                locked, reason or f"код {body.get('ErrorCode')}"
                            )
                    await create_application_event(
                        db=db,
                        application_id=payment.application_id,
                        kind=ApplicationEventKind.STATUS_CHANGED,
                        audience=NotificationAudience.ADMIN,
                        title="Касса не пробила чек",
                        message=(
                            f"Т-Банк сообщил об ошибке фискализации"
                            f"{' закрывающего чека' if closing else (' чека предоплаты' if closing is False else '')}"
                            f" (код {body.get('ErrorCode')}{': ' + reason if reason else ''}). "
                            "Оплата при этом прошла. Проверьте кассу в ЛК Т-Бизнеса (аренда, ФН, "
                            "СНО, ФФД) и пробейте чек повторно или чеком коррекции."
                        ),
                        payload={"payment_id": str(payment.id), "error_code": str(body.get("ErrorCode"))},
                        created_by=None,
                    )
            await db.commit()
        return _ok()

    if (
        status_value in _TBANK_SERVICE_NOTIFICATIONS
        or str(body.get("NotificationType") or "") in _TBANK_SERVICE_TYPES
    ):
        await journal(status_value or str(body.get("NotificationType"))[:40])
        return _ok()

    payment = await find_payment_for_notification(
        db,
        provider_payment_id=provider_payment_id,
        order_id=None if order_id is None else str(order_id),
    )
    if payment is None:
        # Не наш заказ (например, тест с другого стенда на том же терминале).
        # OK, чтобы банк не повторял месяц; тело — в журнале.
        log.warning("T-Bank notification for unknown payment: PaymentId=%r", raw_pid)
        await journal(f"unknown:{status_value}")
        return _ok()

    if await _already_stored(db, provider="tbank", external_id=event_id):
        return _ok()  # повтор уже обработанного уведомления — лишний раз банк не спрашиваем

    bank_id = payment.provider_payment_id or provider_payment_id
    if not bank_id:
        await journal(f"no_payment_id:{status_value}")
        return _ok()

    locked = await lock_payment(db, payment.id)
    if locked is None:
        return _ok()
    try:
        state = await service.get_state(payment_id=bank_id)
    except TBankError as e:
        # Состояние не узнали — не делаем вид, что обработали: банк повторит.
        log.warning("T-Bank GetState failed on notification for %s: %s", payment.id, e)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Т-Банк не ответил, повторите позже"
        ) from e

    if locked.provider_payment_id is None:
        # PaymentId взят из тела уведомления (Init не успел сохранить свой) —
        # убеждаемся у банка, что это платёж именно этого заказа. Иначе сдвигом
        # границ в теле (цифры из Pan в PaymentId) можно было бы подставить
        # состояние другого нашего платежа.
        if state.order_id != str(locked.id):
            log.warning(
                "T-Bank GetState order mismatch: payment=%s bank_id=%s order=%r",
                locked.id, bank_id, state.order_id,
            )
            await db.rollback()
            await journal(f"order_mismatch:{status_value}")
            return _ok()
        locked.provider_payment_id = str(state.payment_id)
    await apply_bank_state(
        db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks
    )
    locked.provider_checked_at = utcnow()
    locked.last_callback_payload = stored_body
    if not await _store_idempotent(
        db, provider="tbank", external_id=event_id, event_type=status_value, body=stored_body
    ):
        return _ok()  # параллельный повтор успел раньше — его изменения и остаются
    await db.commit()
    return _ok()
