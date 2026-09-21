"""Фоновая сверка платежей Т-Банка: подстраховка на случай потерянного уведомления.

Основной путь — уведомления банка и сверка при открытии страницы оплаты. Но
если уведомление потерялось (наш сервер лежал, банк исчерпал повторы), а
клиент закрыл вкладку, оплата так и висела бы «ожидает». Раз в 10 минут
спрашиваем банк про:

- открытые ссылки (awaiting_user) и возвраты «в пути» (refund_requested);
- ссылки, закрытые только у нас (банк отказал в Cancel из AUTH_FAIL и т.п.,
  provider_status остался «денег нет»): до своего срока банк ещё может их
  принять — такую оплату надо засчитать.

Каждая сверка — тот же recheck_payment, что и у страницы оплаты: слот с
троттлингом и SKIP LOCKED, отпечаток платежа, автомат apply_bank_state.

Там же — закрывающие чеки 54-ФЗ (app/services/tbank_receipts.py): досылаем
те, что не ушли сразу при выдаче документов (банк не ответил, процесс
перезапустился), и переводим зависшие отправки в «неизвестно» с алертом.

Запуск (cron на проде, см. deploy/setup-ops.sh):

    python -m scripts.reconcile_tbank_payments [--limit 200]
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.auth import utcnow
from app.database import AsyncSessionLocal
from app.enums import PaymentProvider, PaymentStatus
from app.models.payment import Payment
from app.services.tbank_acquiring import TBankNotConfigured, get_tbank_service
from app.services.tbank_payments import NON_MONEY, recheck_payment
from app.services.tbank_receipts import (
    closing_receipts_to_send,
    expire_stale_sending,
    send_closing_receipt,
)

# Свежие платежи не трогаем: их статус придёт уведомлением или сверкой страницы.
_MIN_AGE = timedelta(minutes=2)
# Не спрашивать банк про один платёж чаще этого.
_CHECK_EVERY = timedelta(minutes=10)
# Закрытую у нас ссылку банк может принять до своего срока (+ запас на часы).
_LOCALLY_CLOSED_GRACE = timedelta(hours=1)


async def _run(limit: int) -> Counter:
    try:
        terminal_key = get_tbank_service().terminal_key
    except TBankNotConfigured:
        return Counter()  # терминал не подключён — молча: крон дёргает каждые 10 минут

    now = utcnow()
    in_flight = Payment.status.in_(
        [PaymentStatus.AWAITING_USER.value, PaymentStatus.REFUND_REQUESTED.value]
    )
    closed_only_here = and_(
        Payment.status.in_([PaymentStatus.EXPIRED.value, PaymentStatus.CANCELLED.value]),
        Payment.provider_status.in_(sorted(NON_MONEY)),
        Payment.expires_at > now - _LOCALLY_CLOSED_GRACE,
    )
    stmt = (
        select(Payment.id)
        .where(
            Payment.provider == PaymentProvider.TBANK.value,
            Payment.provider_account == terminal_key,
            Payment.provider_payment_id.is_not(None),
            Payment.created_at < now - _MIN_AGE,
            or_(Payment.provider_checked_at.is_(None), Payment.provider_checked_at < now - _CHECK_EVERY),
            or_(in_flight, closed_only_here),
        )
        .order_by(Payment.provider_checked_at.asc().nulls_first())
        .limit(limit)
    )

    moved: Counter = Counter()
    async with AsyncSessionLocal() as db:
        ids = (await db.execute(stmt)).scalars().all()
    for payment_id in ids:
        # Своя сессия на платёж: сбой одного не мешает остальным.
        async with AsyncSessionLocal() as db:
            payment = await db.get(Payment, payment_id)
            if payment is None:
                continue
            before = payment.status
            try:
                payment = await recheck_payment(db, payment)
            except Exception as e:  # noqa: BLE001 — сверка не должна падать целиком
                await db.rollback()
                print(f"{payment_id}: ошибка сверки: {e!r}")
                moved["error"] += 1
                continue
            moved[f"{before}->{payment.status}" if payment.status != before else "unchanged"] += 1

    # Закрывающие чеки: сначала зависшие отправки → unknown (их не повторяем
    # вслепую), потом досылка тех, что пора отправить.
    async with AsyncSessionLocal() as db:
        stale = await expire_stale_sending(db, utcnow())
        receipt_ids = await closing_receipts_to_send(db, limit=limit)
    if stale:
        moved["closing_receipt:stale->unknown"] += stale
    for payment_id in receipt_ids:
        async with AsyncSessionLocal() as db:
            try:
                outcome = await send_closing_receipt(db, payment_id)
            except Exception as e:  # noqa: BLE001
                await db.rollback()
                print(f"{payment_id}: ошибка закрывающего чека: {e!r}")
                moved["closing_receipt:error"] += 1
                continue
        if outcome is not None:
            moved[f"closing_receipt:{outcome}"] += 1
    return moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Сверка платежей Т-Банка с банком")
    parser.add_argument("--limit", type=int, default=200, help="Сколько платежей за запуск")
    args = parser.parse_args()
    moved = asyncio.run(_run(args.limit))
    if moved:  # пустые запуски раз в 10 минут лог не засоряют
        changed = {k: v for k, v in moved.items() if k != "unchanged"}
        print(f"{utcnow():%Y-%m-%d %H:%M} проверено: {sum(moved.values())}; изменилось: {changed or 'ничего'}")


if __name__ == "__main__":
    main()
