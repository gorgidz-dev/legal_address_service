"""Чеки 54-ФЗ по оплатам через Т-Банк: предоплата при оплате, полный расчёт при выдаче.

Чеки пробивает облачная касса (OFD Ferma), привязанная к терминалу в ЛК
Т-Бизнеса; мы только передаём банку данные чека (docs/tbank-acquiring.md §7, §10).

Два чека, потому что услуга по оферте (п. 3.3) оказана в момент, когда клиент
получил документы в личном кабинете, а это через несколько дней после оплаты:
- «ПРЕДОПЛАТА 100%» — Receipt в Init, ставка НДС расчётная (22/122);
- «ПОЛНЫЙ РАСЧЁТ» — /cashbox/SendClosingReceipt при переходе заявки в
  «Готово для клиента», ставка 22%, оплата зачётом аванса.

Закрывающий чек — самое опасное место: у метода нет ключа идемпотентности,
и повтор после обрыва связи может пробить ВТОРОЙ чек (исправлять пришлось бы
чеком коррекции). Поэтому состояние хранится в платеже и отправка идёт через
атомарный захват строки:

    NULL ──(документы выданы)──▶ due ──(захват)──▶ sending ──▶ sent
                                  ▲                  │
                                  ├──────────────────┤ запрос точно не ушёл
                                  │                  │ (предохранитель, нет
                                  │                  │ соединения): повтор кроном
                                  └──── failed ◀─────┤ банк явно отказал:
                                   (повтор кроном,   │ повтор безопасен
                                    до N попыток)    │
                                                     └──▶ unknown: связь
                                                          оборвалась — решает
                                                          админ по ЛК

Из `unknown` автоматически НЕ повторяем: админ смотрит в ЛК Т-Бизнеса
(«Операции» → платёж), есть ли закрывающий чек, и либо отмечает его
отправленным, либо отправляет заново (POST /payments/{id}/closing-receipt).

Закрывающий чек — один на заявку: при повторном входе в «Готово» (после
спора) и при лишней оплате второй не заводится. После частичного возврата в
ЛК сумма чека предоплаты больше не верна — такой чек только вручную в ЛК.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.config import settings
from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    NotificationAudience,
    PaymentProvider,
    PaymentStatus,
)
from app.models.payment import Payment
from app.services.notification_events import create_application_event
from app.services.tbank_acquiring import TBankError, TBankNotConfigured, get_tbank_service

log = logging.getLogger(__name__)

DUE = "due"
SENDING = "sending"
SENT = "sent"
FAILED = "failed"
UNKNOWN = "unknown"

# Статусы заявки, в которых документы клиенту уже выданы (услуга оказана).
DOCUMENTS_ISSUED = frozenset({
    ApplicationStatus.READY_FOR_CLIENT.value,
    ApplicationStatus.COMPLETED.value,
    ApplicationStatus.DISPUTE.value,
})

# Отправка, «зависшая» дольше этого (упал процесс посреди запроса к банку), —
# это тоже «неизвестно, ушёл ли чек». С запасом больше таймаута запроса к банку.
SENDING_STALE_AFTER = timedelta(minutes=10)

_PARTIAL_REFUNDED = "PARTIAL_REFUNDED"  # статус банка, см. tbank_payments

# Ставка чека предоплаты — расчётная от ставки полного расчёта (п.4 ст.164 НК;
# письмо ФНС от 15.12.2025 № АБ-4-20/11248@: предоплата — 22/122, полный расчёт — 22%).
_PREPAYMENT_VAT = {
    "none": "none",
    "vat0": "vat0",
    "vat5": "vat105",
    "vat7": "vat107",
    "vat10": "vat110",
    "vat22": "vat122",
}

_NAME_MAX = 128  # тег 1030 в ФФД 1.2 / maxLength в OpenAPI
_EMAIL_MAX = 64  # maxLength Email/Phone в Receipt

# Чек предоплаты действительно есть — именно JSON-объект. Колонка пишет None
# как SQL NULL (none_as_null), а проверка типа — страховка от JSON 'null'.
_HAS_RECEIPT = func.jsonb_typeof(Payment.receipt) == "object"

# Закрывающий чек по платежу возможен: оплачен, есть чек предоплаты, известен
# PaymentId, и не было частичного возврата (после него сумма чека неверна).
_CLOSABLE = and_(
    Payment.status == PaymentStatus.SUCCEEDED.value,
    _HAS_RECEIPT,
    Payment.provider_payment_id.is_not(None),
    Payment.refunded_kopeks == 0,
    Payment.provider_status.is_distinct_from(_PARTIAL_REFUNDED),
)


def _retry_allowed():
    return or_(
        Payment.closing_receipt_status == DUE,
        and_(
            Payment.closing_receipt_status == FAILED,
            Payment.closing_receipt_attempts < settings.tbank_closing_receipt_max_attempts,
        ),
    )


class ReceiptContactMissing(ValueError):
    """У покупателя нет ни e-mail, ни телефона — чек некуда отправить (54-ФЗ, тег 1008)."""


def _buyer_contact(email: Optional[str], phone: Optional[str]) -> dict[str, str]:
    email = (email or "").strip()
    if email and "@" in email and len(email) <= _EMAIL_MAX:
        return {"Email": email}
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits[0] in "78":
        return {"Phone": "+7" + digits[1:]}
    if len(digits) == 10:
        return {"Phone": "+7" + digits}
    raise ReceiptContactMissing("Для чека нужен e-mail или телефон покупателя")


def build_prepayment_receipt(
    *, amount_kopeks: int, email: Optional[str], phone: Optional[str]
) -> dict[str, Any]:
    """Receipt для Init: одна позиция «предоплата 100%» на всю сумму.

    Одна позиция, а не разбивка по строкам цены: по оферте ООО продаёт одну
    собственную услугу (п. 2), а «аренда адреса» в строках цены — договор
    клиента с собственником, который ООО не заключает.
    """
    item = {
        "Name": settings.tbank_receipt_item_name[:_NAME_MAX],
        "Price": int(amount_kopeks),
        "Quantity": 1,
        "Amount": int(amount_kopeks),
        "Tax": _PREPAYMENT_VAT[settings.tbank_receipt_vat],
        "PaymentMethod": "full_prepayment",
        "PaymentObject": "service",
        "MeasurementUnit": settings.tbank_receipt_measurement_unit,
    }
    receipt: dict[str, Any] = {
        "Taxation": settings.tbank_receipt_taxation,
        "Items": [item],
        **_buyer_contact(email, phone),
    }
    if settings.tbank_receipt_ffd_version:
        receipt["FfdVersion"] = settings.tbank_receipt_ffd_version
    return receipt


def build_closing_receipt(prepayment: dict[str, Any]) -> dict[str, Any]:
    """Закрывающий чек по снимку чека предоплаты.

    Позиции и покупатель — те же, признак — «полный расчёт», ставка — текущая
    ставка полного расчёта: её определяет дата оказания услуги, а не дата
    предоплаты (так ФНС разобрала переход 20→22%: письмо от 15.12.2025
    № АБ-4-20/11248@). Оплата — зачётом аванса (тег 1215), без новых денег.
    """
    receipt = copy.deepcopy(prepayment)
    total = 0
    for item in receipt["Items"]:
        item["PaymentMethod"] = "full_payment"
        item["Tax"] = settings.tbank_receipt_vat
        total += int(item["Amount"])
    receipt["Taxation"] = settings.tbank_receipt_taxation
    # Electronic обязателен по схеме; 0 — новых безналичных денег в этом чеке нет.
    # Сумма видов оплаты = сумме позиций (требование схемы Payments).
    receipt["Payments"] = {"Electronic": 0, "AdvancePayment": total}
    return receipt


# ------------------------------------------------------------------
# Постановка в очередь (в транзакции перехода заявки)
# ------------------------------------------------------------------


def _paid_order_key(payment: Payment):
    paid = payment.paid_at or payment.created_at
    return (paid is not None, paid, payment.created_at)


async def mark_closing_receipt_due(db: AsyncSession, application_id: UUID) -> Optional[Payment]:
    """Документы выданы — пора закрывающего чека. Возвращает платёж, поставленный в очередь.

    Один закрывающий чек на заявку: если по какому-либо платежу заявки он уже
    заводился (любое состояние), второй не заводим — ни при повторном входе
    в «Готово» после спора, ни при появлении лишней оплаты. Из нескольких
    оплаченных закрываем самый свежий, а про остальные предупреждаем: лишний
    платёж надо вернуть, а не закрывать.
    """
    stmt = (
        select(Payment)
        .where(
            Payment.application_id == application_id,
            Payment.provider == PaymentProvider.TBANK.value,
        )
        .order_by(Payment.paid_at.desc().nulls_last(), Payment.created_at.desc())
        .with_for_update()
    )
    payments = list((await db.execute(stmt)).scalars().all())
    if any(p.closing_receipt_status is not None for p in payments):
        return None
    paid = [
        p for p in payments
        if p.status == PaymentStatus.SUCCEEDED.value and isinstance(p.receipt, dict)
    ]
    if not paid:
        return None
    paid.sort(key=_paid_order_key, reverse=True)
    target = paid[0]
    if len(paid) > 1:
        await _admin_event(
            db, target,
            title="По заявке несколько оплат",
            message=(
                f"Оплаченных платежей по заявке: {len(paid)}. Закрывающий чек уйдёт по "
                "последнему; лишние оплаты верните — по ним закрывающий чек не пробивается."
            ),
        )
    if target.provider_status == _PARTIAL_REFUNDED or (target.refunded_kopeks or 0) > 0:
        # Сумма в чеке предоплаты больше не совпадает с оставшимися деньгами.
        give_up_closing_receipt(target, "После частичного возврата — закрывающий чек на остаток только в ЛК")
        await _admin_event(
            db, target,
            title="Закрывающий чек — вручную",
            message=(
                "По платежу был частичный возврат в ЛК Т-Бизнеса, поэтому закрывающий чек "
                "«полный расчёт» на остаток пробейте в ЛК («Операции» → платёж)."
            ),
        )
        return None
    target.closing_receipt_status = DUE
    target.closing_receipt_error = None
    return target


def give_up_closing_receipt(payment: Payment, reason: str) -> None:
    """Автоматика больше не трогает закрывающий чек: только вручную (админ/ЛК)."""
    payment.closing_receipt_status = FAILED
    payment.closing_receipt_attempts = max(
        payment.closing_receipt_attempts or 0, settings.tbank_closing_receipt_max_attempts
    )
    payment.closing_receipt_error = reason[:500]


# ------------------------------------------------------------------
# Отправка
# ------------------------------------------------------------------


async def _claim(db: AsyncSession, payment_id: UUID, now: datetime) -> bool:
    """Атомарно занять отправку: due (или failed с попытками в запасе) → sending.

    Условный UPDATE — из крона и фоновой задачи отправит ровно один. Платёж
    должен быть оплачен: пока идёт возврат, закрывающий чек не нужен (а если
    возврат не прошёл, платёж снова succeeded и чек уйдёт со следующей сверкой).
    """
    stmt = (
        update(Payment)
        .where(Payment.id == payment_id, _CLOSABLE, _retry_allowed())
        .values(
            closing_receipt_status=SENDING,
            closing_receipt_attempts=Payment.closing_receipt_attempts + 1,
            # Во время отправки — время попытки (по нему ловим зависшие), после — время отправки.
            closing_receipt_at=now,
        )
        .returning(Payment.id)
        .execution_options(synchronize_session=False)
    )
    claimed = (await db.execute(stmt)).scalar_one_or_none() is not None
    await db.commit()  # фиксируем захват ДО похода в банк
    return claimed


async def send_closing_receipt(db: AsyncSession, payment_id: UUID) -> Optional[str]:
    """Отправить закрывающий чек, если он причитается. Возвращает итоговый статус или None.

    Ошибки банка не выбрасывает: чек — фоновая обязанность, итог записан в
    платёж, о проблемах админ узнаёт событием.
    """
    try:
        service = get_tbank_service()
    except TBankNotConfigured:
        return None
    if not await _claim(db, payment_id, utcnow()):
        return None
    payment = (
        await db.execute(
            select(Payment).where(Payment.id == payment_id).execution_options(populate_existing=True)
        )
    ).scalar_one()

    if payment.provider_account and payment.provider_account != service.terminal_key:
        # Платёж другого терминала (DEMO до перехода на боевой): через текущий
        # терминал его чек не отправить. Повторять бессмысленно.
        give_up_closing_receipt(payment, "Платёж проведён на другом терминале Т-Банка")
        await _admin_event(
            db, payment,
            title="Закрывающий чек не отправлен",
            message=(
                "Платёж проведён на другом терминале Т-Банка — закрывающий чек "
                "отправьте из ЛК того терминала («Операции» → платёж)."
            ),
        )
        await db.commit()
        return FAILED

    try:
        closing = build_closing_receipt(payment.receipt)
    except (TypeError, KeyError, ValueError) as e:
        # Снимок чека предоплаты не читается — запроса в банк не было.
        give_up_closing_receipt(payment, f"Снимок чека предоплаты повреждён: {e!r}")
        await _admin_event(
            db, payment,
            title="Закрывающий чек не отправлен",
            message="Не удалось собрать закрывающий чек из чека предоплаты — пробейте его в ЛК.",
        )
        await db.commit()
        return FAILED

    try:
        await service.send_closing_receipt(payment_id=payment.provider_payment_id, receipt=closing)
    except TBankError as e:
        payment.closing_receipt_error = str(e)[:500]
        if e.not_sent:
            # Запрос точно не дошёл до банка (предохранитель, нет соединения):
            # вернуть в очередь, попытку не считать, крон повторит — без алерта.
            payment.closing_receipt_status = DUE
            payment.closing_receipt_attempts = max(0, payment.closing_receipt_attempts - 1)
            await db.commit()
            return DUE
        if e.is_business_refusal:
            payment.closing_receipt_status = FAILED
            log.warning("Closing receipt refused for payment %s: %s", payment.id, e)
            if payment.closing_receipt_attempts >= settings.tbank_closing_receipt_max_attempts:
                await _admin_event(
                    db, payment,
                    title="Закрывающий чек не отправлен",
                    message=(
                        f"Т-Банк отказал в закрывающем чеке ({e}). Автоповторы исчерпаны. "
                        "Проверьте кассу в ЛК Т-Бизнеса (ФФД, СНО, оплата аренды, ФН) и "
                        "отправьте чек повторно из карточки платежа или из ЛК."
                    ),
                )
        else:
            # Банк мог чек и принять — повтор вслепую пробил бы второй.
            payment.closing_receipt_status = UNKNOWN
            log.warning("Closing receipt outcome unknown for payment %s: %s", payment.id, e)
            await _admin_event(db, payment, title=_UNKNOWN_TITLE, message=_UNKNOWN_MESSAGE)
        await db.commit()
        return payment.closing_receipt_status

    payment.closing_receipt_status = SENT
    payment.closing_receipt_at = utcnow()
    payment.closing_receipt_error = None
    await db.commit()
    return SENT


_UNKNOWN_TITLE = "Проверьте закрывающий чек"
_UNKNOWN_MESSAGE = (
    "Связь с Т-Банком оборвалась при отправке закрывающего чека — неизвестно, "
    "пробит ли он. Откройте ЛК Т-Бизнеса → «Операции» → этот платёж. Если "
    "закрывающий чек есть — отметьте его отправленным; если нет — отправьте "
    "повторно. Автоматически не повторяем, чтобы не пробить второй чек."
)


async def expire_stale_sending(db: AsyncSession, now: datetime) -> int:
    """Зависшие отправки (упал процесс посреди запроса к банку) → unknown + алерт."""
    stmt = (
        update(Payment)
        .where(
            Payment.closing_receipt_status == SENDING,
            Payment.closing_receipt_at < now - SENDING_STALE_AFTER,
        )
        .values(
            closing_receipt_status=UNKNOWN,
            closing_receipt_error="Отправка прервалась: процесс остановился посреди запроса к банку",
        )
        .returning(Payment.id)
        .execution_options(synchronize_session=False)
    )
    ids = list((await db.execute(stmt)).scalars().all())
    for payment_id in ids:
        payment = await db.get(Payment, payment_id)
        if payment is not None:
            await _admin_event(db, payment, title=_UNKNOWN_TITLE, message=_UNKNOWN_MESSAGE)
    await db.commit()
    return len(ids)


async def closing_receipts_to_send(
    db: AsyncSession, *, application_id: Optional[UUID] = None, limit: int = 100
) -> list[UUID]:
    """Id платежей, по которым пора (до)отправить закрывающий чек."""
    stmt = select(Payment.id).where(_CLOSABLE, _retry_allowed())
    if application_id is not None:
        stmt = stmt.where(Payment.application_id == application_id)
    stmt = stmt.order_by(Payment.closing_receipt_at.asc().nulls_first()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def send_due_for_application(application_id: UUID) -> None:
    """Фоновая задача после выдачи документов: отправить чек сразу, не ждать крона."""
    from app.database import AsyncSessionLocal  # локально: модуль грузится и без БД

    try:
        async with AsyncSessionLocal() as db:
            for payment_id in await closing_receipts_to_send(db, application_id=application_id):
                await send_closing_receipt(db, payment_id)
    except Exception:  # noqa: BLE001 — фоновая задача не должна ронять ответ; крон повторит
        log.exception("Closing receipt background send failed for application %s", application_id)


# ------------------------------------------------------------------
# Возвраты и отказы кассы
# ------------------------------------------------------------------


async def alert_if_closing_receipt_may_exist(db: AsyncSession, payment: Payment) -> None:
    """Возврат по платежу, по которому закрывающий чек пробит или мог быть пробит.

    Полный Cancel идёт без Receipt, и какой признак расчёта банк поставит в
    автоматический чек возврата, в документации не описано, — сверить в ЛК.
    """
    status = payment.closing_receipt_status
    if status == SENT:
        message = (
            "Возврат оформлен после закрывающего чека «полный расчёт». Сверьте в ЛК "
            "Т-Бизнеса, что чек возврата пробит с признаком полного расчёта."
        )
    elif status in (SENDING, UNKNOWN):
        message = (
            "Возврат оформлен, когда закрывающий чек «полный расчёт» мог быть уже пробит. "
            "Сверьте в ЛК Т-Бизнеса оба чека — закрывающий и чек возврата."
        )
    else:
        return
    await _admin_event(db, payment, title="Проверьте чек возврата", message=message)


def receipt_notification_is_closing(body: dict[str, Any]) -> Optional[bool]:
    """По уведомлению RECEIPT понять, про какой чек речь: True — закрывающий,
    False — предоплата, None — не понять (состав уведомления не документирован)."""
    receipt = body.get("Receipt")
    items = receipt.get("Items") if isinstance(receipt, dict) else None
    if not isinstance(items, list) or not items:
        return None
    methods = {item.get("PaymentMethod") for item in items if isinstance(item, dict)}
    if "full_payment" in methods:
        return True
    if methods & {"full_prepayment", "prepayment", "advance"}:
        return False
    return None


def mark_closing_receipt_rejected_by_kassa(payment: Payment, reason: str) -> None:
    """Касса не пробила ОТПРАВЛЕННЫЙ закрывающий чек — открыть ручной повтор.

    Автоповтор не включаем: причину (ФН, аренда, СНО) сначала устраняют в ЛК.
    """
    give_up_closing_receipt(payment, f"Касса не пробила закрывающий чек: {reason}")


async def _admin_event(db: AsyncSession, payment: Payment, *, title: str, message: str) -> None:
    await create_application_event(
        db=db,
        application_id=payment.application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.ADMIN,
        title=title,
        message=message,
        payload={"payment_id": str(payment.id), "closing_receipt": payment.closing_receipt_status},
        created_by=None,
    )
