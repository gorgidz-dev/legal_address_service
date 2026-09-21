"""Что делать с платежом и заявкой по состоянию платежа у Т-Банка.

Главный принцип (выработан двумя раундами адверсариальной ревизии):
решения о деньгах принимаются ТОЛЬКО по состоянию, которое банк отдаёт сам —
методом GetState или в ответе на наш Cancel. Уведомление банка — лишь сигнал
«что-то изменилось, спроси». Причина: подпись уведомления склеивает значения
БЕЗ разделителей, а набор полей не фиксирован, поэтому тело можно подделать
сдвигом границ, лишним или переименованным полем — при верной подписи. Ответ
GetState приходит по TLS напрямую от банка, подделать его нельзя.

Прочие правила:
- «Деньги получены» — только CONFIRMED, с суммой, совпавшей с заказом.
- Переходы только вперёд; вызывающий держит FOR UPDATE строки платежа.
- CONFIRMED засчитывается и по «мёртвому» у нас платежу — деньги реальные.
- Возврат через систему — только полный (частичные — в ЛК Т-Бизнеса: у
  уведомлений о возврате нет id операции, и несколько частичных неотличимы).
- Отказ возврата засчитываем только окончательный (REJECTED от банка);
  неоднозначное «банк всё ещё показывает оплату» — ждём, повтор тем же ключом.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.config import settings
from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    NotificationAudience,
    PaymentProvider,
    PaymentStatus,
    UserRole,
)
from app.models.application import Application
from app.models.payment import Payment
from app.models.user import User
from app.services.notification_events import create_application_event
from app.services.tbank_acquiring import TBankError, TBankNotConfigured, get_tbank_service

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Группы статусов банка (справочник: /eacq/intro/developer/operation-statuses)
# ------------------------------------------------------------------

PAID = "CONFIRMED"
# Платёж ещё идёт. Колонке «Конечный» из справочника не верим — там NEW и
# AUTHORIZED помечены конечными, хотя переходы из них есть.
IN_PROGRESS = frozenset({
    "NEW", "FORM_SHOWED", "PREAUTHORIZING", "AUTHORIZING", "3DS_CHECKING",
    "3DS_CHECKED", "AUTH_FAIL", "PAY_CHECKING", "AUTHORIZED", "CONFIRMING",
    "CONFIRM_CHECKING", "REVERSING",
})
# Из них «деньги сейчас движутся» — ссылку не трогаем, пока не протухнет всерьёз.
MONEY_MOVING = frozenset({
    "PREAUTHORIZING", "AUTHORIZING", "3DS_CHECKED", "PAY_CHECKING",
    "AUTHORIZED", "CONFIRMING", "CONFIRM_CHECKING", "REVERSING",
})
# Денег по платежу у банка нет и не было: закрыть ссылку у себя безопасно,
# даже если банк откажет в Cancel (из AUTH_FAIL/3DS_CHECKING он в документации
# не описан).
NON_MONEY = frozenset({"NEW", "FORM_SHOWED", "AUTH_FAIL", "3DS_CHECKING"})
UNPAID_FINAL = {  # оплаты не было и не будет
    "REJECTED": PaymentStatus.FAILED,
    "ATTEMPTS_EXPIRED": PaymentStatus.FAILED,
    "DEADLINE_EXPIRED": PaymentStatus.EXPIRED,
    "CANCELED": PaymentStatus.CANCELLED,
    "REVERSED": PaymentStatus.CANCELLED,
    "PARTIAL_REVERSED": PaymentStatus.CANCELLED,
}
VOIDED = frozenset({"CANCELED", "REVERSED", "PARTIAL_REVERSED", "DEADLINE_EXPIRED"})
REFUND_IN_PROGRESS = frozenset({"REFUNDING", "ASYNC_REFUNDING"})
REFUNDED = "REFUNDED"
PARTIAL_REFUNDED = "PARTIAL_REFUNDED"

AMOUNT_MISMATCH = "CONFIRMED:AMOUNT_MISMATCH"

OPEN = frozenset({PaymentStatus.PENDING.value, PaymentStatus.AWAITING_USER.value})
_UNPAID_CLOSED = frozenset({
    PaymentStatus.FAILED.value, PaymentStatus.EXPIRED.value, PaymentStatus.CANCELLED.value,
})

# Страница оплаты опрашивает GET /payments/{id} раз в 3 секунды — к банку за
# статусом ходим не чаще раза в 20 секунд.
RECHECK_INTERVAL = timedelta(seconds=20)

# Поля уведомления, которые не храним: срок действия карты — лишнее ПДн.
_DROP_FROM_STORED = frozenset({"ExpDate"})


# ------------------------------------------------------------------
# Мелкие помощники
# ------------------------------------------------------------------


def is_demo_terminal(terminal_key: Optional[str]) -> bool:
    return bool(terminal_key) and terminal_key.upper().endswith("DEMO")


def may_use_test_terminal(user: Optional[User]) -> bool:
    """Платить на DEMO-терминале могут только админы и ПОДТВЕРДИВШИЕ почту тестировщики.

    Без подтверждения почты любой мог бы подать заявку с адресом тестировщика
    (аккаунт создаётся вместе с заявкой) и «оплатить» её тестовой картой.
    """
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    if getattr(user, "email_verified_at", None) is None:
        return False
    allowed = {
        email.strip().lower()
        for email in settings.tbank_test_payer_emails.split(",")
        if email.strip()
    }
    return (user.email or "").lower() in allowed


def sanitize_for_storage(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k not in _DROP_FROM_STORED}


def notification_event_id(body: dict[str, Any]) -> str:
    """Ключ для журнала уведомлений: повтор банка присылает то же тело.

    На решения он не влияет — состояние всё равно берётся у банка, поэтому
    совпадение ключей у разных событий ничего не ломает, а лишь экономит запрос.
    """
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]
    return f"{body.get('PaymentId')}:{body.get('Status')}:{digest}"


def fingerprint(payment: Payment) -> tuple:
    """Всё, что меняет автомат: по нему видно, трогал ли платёж кто-то ещё."""
    return (
        payment.status,
        payment.provider_status,
        payment.refunded_kopeks or 0,
        payment.refund_attempts or 0,
        payment.refund_key,
    )


# ------------------------------------------------------------------
# Блокировки и поиск
# ------------------------------------------------------------------


async def lock_payment(
    db: AsyncSession, payment_id: UUID, *, skip_locked: bool = False
) -> Optional[Payment]:
    """Перечитать платёж под FOR UPDATE (skip_locked — не ждать чужую блокировку)."""
    stmt = (
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update(skip_locked=skip_locked)
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def find_payment_for_notification(
    db: AsyncSession, *, provider_payment_id: Optional[str], order_id: Optional[str]
) -> Optional[Payment]:
    """Наш платёж по уведомлению: по PaymentId банка, иначе по OrderId (= наш id)."""
    if provider_payment_id:
        stmt = select(Payment).where(
            Payment.provider == PaymentProvider.TBANK.value,
            Payment.provider_payment_id == provider_payment_id,
        )
        payment = (await db.execute(stmt)).scalar_one_or_none()
        if payment is not None:
            return payment
    if order_id:
        try:
            payment_uuid = UUID(str(order_id))
        except ValueError:
            return None
        payment = await db.get(Payment, payment_uuid)
        if payment is not None and payment.provider == PaymentProvider.TBANK.value:
            return payment
    return None


# ------------------------------------------------------------------
# Автомат: применить СОСТОЯНИЕ БАНКА (GetState или ответ Cancel)
# ------------------------------------------------------------------


async def apply_bank_state(
    db: AsyncSession,
    *,
    payment: Payment,
    status: str,
    amount_kopeks: Optional[int],
    voided_as: Optional[PaymentStatus] = None,
) -> bool:
    """Применить статус, который сообщил САМ банк. Возвращает True, если наш статус изменился.

    voided_as — чем считать отмену неоплаченной ссылки (EXPIRED при замене
    ссылки, CANCELLED при отмене админом); без него — по таблице UNPAID_FINAL.
    """
    local = payment.status

    if status == PAID:
        if local in (PaymentStatus.SUCCEEDED.value, PaymentStatus.REFUNDED.value):
            return False
        if local == PaymentStatus.REFUND_REQUESTED.value:
            # Возврат «в пути», а банк всё ещё показывает оплату: то ли он ещё не
            # начал, то ли не дошёл. Не гадаем — повтор тем же ключом всё решит.
            return False
        if amount_kopeks is not None and amount_kopeks != payment.amount_kopeks:
            if payment.provider_status != AMOUNT_MISMATCH:  # алерт один раз
                await _admin_event(
                    db, payment,
                    title="Сумма оплаты не совпала с заказом",
                    message=(
                        f"Т-Банк показывает оплату {amount_kopeks / 100:.2f} ₽, а заказ был на "
                        f"{payment.amount_kopeks / 100:.2f} ₽. Оплата не засчитана — "
                        "разберитесь в личном кабинете Т-Бизнеса."
                    ),
                )
                log.error(
                    "T-Bank amount mismatch payment=%s bank=%s ours=%s",
                    payment.id, amount_kopeks, payment.amount_kopeks,
                )
            payment.provider_status = AMOUNT_MISMATCH
            return False
        payment.status = PaymentStatus.SUCCEEDED.value
        payment.provider_status = PAID
        payment.paid_at = payment.paid_at or utcnow()
        await _on_paid(db, payment, previous_local=local)
        return True

    if status in IN_PROGRESS:
        if local in OPEN and payment.provider_status != AMOUNT_MISMATCH:
            payment.provider_status = status
        return False

    if status in UNPAID_FINAL:
        if local in OPEN:
            final = voided_as if (voided_as is not None and status in VOIDED) else UNPAID_FINAL[status]
            payment.status = final.value
            payment.provider_status = status
            return True
        if local == PaymentStatus.REFUND_REQUESTED.value and status == "REJECTED":
            await refund_failed(db, payment, reason="Т-Банк отклонил возврат")
            return True
        return False

    if status in REFUND_IN_PROGRESS:
        if local == PaymentStatus.SUCCEEDED.value:
            # Возврат запустили мимо нас — из ЛК Т-Бизнеса (refund_key пуст).
            payment.status = PaymentStatus.REFUND_REQUESTED.value
            payment.provider_status = status
            return True
        if local in OPEN or local in _UNPAID_CLOSED:
            await _paid_and_returned(db, payment, status=status, finished=False)
            return True
        if local == PaymentStatus.REFUND_REQUESTED.value:
            payment.provider_status = status
        return False

    if status == REFUNDED:
        if local in (PaymentStatus.SUCCEEDED.value, PaymentStatus.REFUND_REQUESTED.value):
            payment.status = PaymentStatus.REFUNDED.value
            payment.provider_status = status
            payment.refunded_kopeks = payment.amount_kopeks
            payment.refunded_at = utcnow()
            payment.refund_key = None
            await _client_event(
                db, payment, title="Деньги возвращены",
                message=(
                    f"Возврат {payment.amount_kopeks / 100:.2f} ₽ оформлен. Обычно деньги "
                    "приходят на счёт за несколько дней, в редких случаях — до 30 дней."
                ),
            )
            await _admin_event(
                db, payment, title="Возврат выполнен",
                message=f"Возвращено {payment.amount_kopeks / 100:.2f} ₽.",
            )
            return True
        if local in OPEN or local in _UNPAID_CLOSED:
            await _paid_and_returned(db, payment, status=status, finished=True)
            return True
        return False

    if status == PARTIAL_REFUNDED:
        if (
            local in (PaymentStatus.SUCCEEDED.value, PaymentStatus.REFUND_REQUESTED.value)
            and payment.provider_status != PARTIAL_REFUNDED
        ):
            # Частичный возврат делают только в ЛК: сумма в API банка неоднозначна,
            # поэтому не выдумываем её, а просим сверить.
            payment.status = PaymentStatus.SUCCEEDED.value
            payment.provider_status = status
            payment.refund_key = None
            await _admin_event(
                db, payment,
                title="Частичный возврат в ЛК Т-Бизнеса",
                message=(
                    "Т-Банк показывает частичный возврат по платежу. В учёте uradres.net "
                    "его сумма не отражена — сверьте в ЛК. Дальнейшие возвраты по этому "
                    "платежу тоже оформляйте в ЛК."
                ),
            )
            return True
        return False

    log.warning("T-Bank: неизвестный статус %s для платежа %s — не меняем", status, payment.id)
    return False


# ------------------------------------------------------------------
# Сверка с банком (страница оплаты и фоновая задача)
# ------------------------------------------------------------------


async def claim_recheck_slot(db: AsyncSession, payment_id: UUID, now: datetime) -> bool:
    """Атомарно занять право сходить в банк за статусом этого платежа.

    Условный UPDATE: из N одновременных опросов в банк пойдёт один, отметка
    ставится ДО похода (неудачная попытка тоже троттлится). SKIP LOCKED — если
    строку держит обработчик возврата/отмены, не ждём его (иначе опрос держал
    бы соединение из пула всё время чужого запроса в банк). Commit сразу
    отпускает соединение: медленный банк не должен держать пул базы.
    """
    locked_row = (
        select(Payment.id)
        .where(
            Payment.id == payment_id,
            or_(
                Payment.provider_checked_at.is_(None),
                Payment.provider_checked_at < now - RECHECK_INTERVAL,
            ),
        )
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    stmt = (
        update(Payment)
        .where(Payment.id == locked_row)
        .values(provider_checked_at=now)
        .returning(Payment.id)
        .execution_options(synchronize_session=False)
    )
    claimed = (await db.execute(stmt)).scalar_one_or_none() is not None
    await db.commit()  # expire_on_commit=False — объекты сессии остаются читаемыми
    return claimed


async def recheck_payment(db: AsyncSession, payment: Payment) -> Payment:
    """Сверить платёж с банком на случай потерянного уведомления. Ошибки не мешают ответу."""
    try:
        service = get_tbank_service()
    except TBankNotConfigured:
        return payment
    if payment.provider_account and payment.provider_account != service.terminal_key:
        return payment  # платёж другого терминала — текущий о нём не знает
    payment_id, bank_id = payment.id, payment.provider_payment_id
    if not bank_id or not await claim_recheck_slot(db, payment_id, utcnow()):
        return payment
    snapshot = fingerprint(payment)
    try:
        state = await service.get_state(payment_id=bank_id)
    except TBankError:
        return payment  # отметка уже стоит — следующий опрос не ударит в банк сразу же
    locked = await lock_payment(db, payment_id, skip_locked=True)
    if locked is None:
        return payment  # строку держит обработчик — он и применит свежее состояние
    if fingerprint(locked) != snapshot:
        # Пока ходили в банк, платёж изменили — наш снимок мог устареть.
        await db.commit()
        return locked
    await apply_bank_state(
        db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks
    )
    await db.commit()
    await db.refresh(locked)
    return locked


# ------------------------------------------------------------------
# Ветки автомата
# ------------------------------------------------------------------


async def _paid_and_returned(db: AsyncSession, payment: Payment, *, status: str, finished: bool) -> None:
    """Покупатель оплатил ссылку, которую мы считали неоплаченной, и деньги уходят обратно.

    Так бывает, когда покупатель платит в миг отмены (Cancel у банка по
    оплаченному платежу — это возврат) или возврат оформили в ЛК. Заявку в
    «оплачена» не переводим: деньги возвращаются.
    """
    payment.paid_at = payment.paid_at or utcnow()
    payment.provider_status = status
    if finished:
        payment.status = PaymentStatus.REFUNDED.value
        payment.refunded_kopeks = payment.amount_kopeks
        payment.refunded_at = utcnow()
    else:
        payment.status = PaymentStatus.REFUND_REQUESTED.value
    rub = payment.amount_kopeks / 100
    await _client_event(
        db, payment, title="Оплата отменена",
        message=(
            f"Ссылку на оплату закрыли в момент, когда вы платили. {rub:.2f} ₽ "
            "возвращаются на ваш счёт — обычно за несколько дней."
        ),
    )
    await _admin_event(
        db, payment, title="Покупатель оплатил в момент отмены",
        message=(
            f"Покупатель оплатил {rub:.2f} ₽ по закрываемой ссылке; Т-Банк возвращает "
            f"деньги (статус {status}). Заявка по-прежнему ждёт оплаты."
        ),
    )


async def refund_failed(db: AsyncSession, payment: Payment, *, reason: str) -> None:
    """Окончательный отказ возврата: деньги остались у магазина."""
    payment.status = PaymentStatus.SUCCEEDED.value
    payment.provider_status = "REJECTED"
    payment.refund_key = None  # следующая попытка — с новым ключом
    await _admin_event(
        db, payment, title="Возврат не прошёл",
        message=(
            f"{reason}: деньги остались у магазина, возврат можно повторить. "
            "Частая причина — не хватает денег на расчётном счёте."
        ),
    )
    # Если возврат начался при закрытии ссылки (заявка так и не стала
    # «оплаченной»), деньги теперь остаются у нас — значит, заявка оплачена.
    application = await _lock_application(db, payment.application_id)
    if application is not None and application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        await _on_paid(db, payment, previous_local=PaymentStatus.REFUND_REQUESTED.value)


async def _lock_application(db: AsyncSession, application_id: UUID) -> Optional[Application]:
    # FOR UPDATE + свежие данные: заявку могла изменить параллельная оплата
    # другой ссылки, а в identity map она лежит с начала запроса.
    stmt = (
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _on_paid(db: AsyncSession, payment: Payment, *, previous_local: str) -> None:
    application = await _lock_application(db, payment.application_id)
    if application is None:
        return
    rub = payment.amount_kopeks / 100

    if is_demo_terminal(payment.provider_account):
        # Защита на сервере: даже если DEMO-ссылка попала к настоящему клиенту и
        # оплачена тестовой картой, заявка не уходит в работу без денег.
        initiator = await db.get(User, payment.initiated_by) if payment.initiated_by else None
        if not may_use_test_terminal(initiator):
            await _admin_event(
                db, payment, title="Тестовая оплата по реальной заявке",
                message=(
                    f"Ссылку DEMO-терминала на {rub:.2f} ₽ оплатили, но создал её не "
                    "тестировщик. Заявка не переведена в «оплачена» — денег нет."
                ),
            )
            return

    if application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        application.status = ApplicationStatus.PAID.value
        await _client_event(
            db, payment, title="Оплата получена",
            message="Заявка переведена в статус «Оплачена» и ушла на проверку.",
            status=ApplicationStatus.PAID.value,
        )
        await _admin_event(
            db, payment, title="Поступила оплата",
            message=f"Платёж {rub:.2f} ₽ подтверждён Т-Банком.",
            status=ApplicationStatus.PAID.value,
        )
        return
    # Деньги пришли, а заявка уже не ждёт оплаты: оплатили по второй ссылке,
    # или заявку отменили, пока покупатель платил.
    await _admin_event(
        db, payment, title="Оплата по заявке, которая её не ждала",
        message=(
            f"Т-Банк подтвердил оплату {rub:.2f} ₽, но заявка в статусе "
            f"«{application.status}» (наш платёж был «{previous_local}»). "
            "Проверьте, не оплачена ли заявка дважды — возможно, нужен возврат."
        ),
    )


async def _client_event(
    db: AsyncSession, payment: Payment, *, title: str, message: str, status: Optional[str] = None
) -> None:
    payload: dict[str, Any] = {"payment_id": str(payment.id)}
    if status:
        payload["status"] = status
    await create_application_event(
        db=db,
        application_id=payment.application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.CLIENT,
        title=title,
        message=message,
        payload=payload,
        created_by=None,
    )


async def _admin_event(
    db: AsyncSession, payment: Payment, *, title: str, message: str, status: Optional[str] = None
) -> None:
    payload: dict[str, Any] = {"payment_id": str(payment.id)}
    if status:
        payload["status"] = status
    await create_application_event(
        db=db,
        application_id=payment.application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.ADMIN,
        title=title,
        message=message,
        payload=payload,
        created_by=None,
    )
