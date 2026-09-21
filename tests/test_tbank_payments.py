"""Автомат статусов Т-Банка: что происходит с платежом и заявкой на каждое состояние банка.

Автомат получает только то, что банк сообщил сам (GetState или ответ Cancel), —
тело уведомления в решения не попадает. Часть сценариев — из адверсариальных
ревизий (помечены «ревизия …»).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.enums import (
    ApplicationStatus,
    NotificationAudience,
    PaymentProvider,
    PaymentStatus,
    UserRole,
)
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.payment import Payment
from app.models.user import User
from app.services import tbank_payments
from app.services.tbank_payments import (
    AMOUNT_MISMATCH,
    apply_bank_state,
    fingerprint,
    may_use_test_terminal,
    notification_event_id,
    refund_failed,
    sanitize_for_storage,
)

AMOUNT = 150_000
LIVE_TERMINAL = "1000000000001"
DEMO_TERMINAL = "1000000000001DEMO"


def _now():
    return datetime.now(timezone.utc)


def _payment(status: PaymentStatus = PaymentStatus.AWAITING_USER, **kw) -> Payment:
    p = Payment(
        application_id=uuid4(),
        provider=PaymentProvider.TBANK.value,
        payer_type="individual",
        status=status.value,
        amount_kopeks=AMOUNT,
        currency="RUR",
        pay_for="Юр. адрес: Тест",
        provider_payment_id="9287980194",
        provider_account=kw.pop("provider_account", LIVE_TERMINAL),
        refunded_kopeks=kw.pop("refunded_kopeks", 0),
        refund_attempts=kw.pop("refund_attempts", 0),
        **kw,
    )
    p.id = uuid4()
    p.created_at = _now()
    p.updated_at = _now()
    return p


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Сессия-заглушка: заявку отдаёт на SELECT … FOR UPDATE, пользователей — через get."""

    def __init__(self, application=None, users=()):
        self._application = application
        self._users = {u.id: u for u in users}
        self.added: list = []

    async def get(self, model, key):
        if model is User:
            return self._users.get(key)
        if self._application is not None and self._application.id == key:
            return self._application
        return None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity") if hasattr(stmt, "column_descriptions") else None
        if entity is Application:
            return _Result(self._application)
        # dispatch_event ищет вебхук-подписки — в юнит-тестах их нет.
        raise RuntimeError("no subscriptions in unit tests")

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def events(self, audience: NotificationAudience | None = None) -> list[ApplicationEvent]:
        found = [e for e in self.added if isinstance(e, ApplicationEvent)]
        if audience is not None:
            found = [e for e in found if e.audience == audience.value]
        return found

    def titles(self, audience: NotificationAudience) -> list[str]:
        return [e.title for e in self.events(audience)]


def _linked(status=PaymentStatus.AWAITING_USER, app_status=ApplicationStatus.AWAITING_PAYMENT, users=(), **kw):
    application = SimpleNamespace(id=uuid4(), status=app_status.value)
    payment = _payment(status, **kw)
    payment.application_id = application.id
    return payment, application, _FakeDB(application, users)


async def _apply(db, payment, status, *, amount=AMOUNT, voided_as=None):
    return await apply_bank_state(
        db, payment=payment, status=status, amount_kopeks=amount, voided_as=voided_as
    )


def _user(role=UserRole.CLIENT, email="tester@example.com", verified=True):
    return SimpleNamespace(
        id=uuid4(), role=role.value, email=email,
        email_verified_at=_now() if verified else None,
    )


# ============================================================
# Оплата
# ============================================================


@pytest.mark.asyncio
async def test_confirmed_marks_paid_and_notifies_client_and_admin() -> None:
    payment, application, db = _linked()
    assert await _apply(db, payment, "CONFIRMED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.provider_status == "CONFIRMED"
    assert payment.paid_at is not None
    assert application.status == ApplicationStatus.PAID.value
    assert db.titles(NotificationAudience.CLIENT) == ["Оплата получена"]
    assert db.titles(NotificationAudience.ADMIN) == ["Поступила оплата"]


@pytest.mark.asyncio
async def test_late_authorized_after_confirmed_does_not_roll_back() -> None:
    payment, application, db = _linked()
    await _apply(db, payment, "CONFIRMED")
    assert not await _apply(db, payment, "AUTHORIZED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.provider_status == "CONFIRMED"


@pytest.mark.asyncio
async def test_repeated_confirmed_is_a_noop() -> None:
    payment, application, db = _linked()
    await _apply(db, payment, "CONFIRMED")
    events_before = len(db.events())
    assert not await _apply(db, payment, "CONFIRMED")
    assert len(db.events()) == events_before


@pytest.mark.asyncio
async def test_authorized_alone_changes_nothing_but_provider_status() -> None:
    payment, application, db = _linked()
    assert not await _apply(db, payment, "AUTHORIZED")
    assert payment.status == PaymentStatus.AWAITING_USER.value
    assert payment.provider_status == "AUTHORIZED"


@pytest.mark.asyncio
async def test_amount_mismatch_is_not_counted_and_alerts_once() -> None:
    # Алерт один раз, а не на каждую сверку раз в 20 секунд.
    payment, application, db = _linked()
    for _ in range(3):
        assert not await _apply(db, payment, "CONFIRMED", amount=100)
    assert payment.status == PaymentStatus.AWAITING_USER.value
    assert payment.provider_status == AMOUNT_MISMATCH
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value
    assert db.titles(NotificationAudience.ADMIN) == ["Сумма оплаты не совпала с заказом"]


@pytest.mark.asyncio
async def test_in_progress_status_does_not_hide_amount_mismatch() -> None:
    payment, application, db = _linked()
    await _apply(db, payment, "CONFIRMED", amount=100)
    await _apply(db, payment, "AUTHORIZED")
    assert payment.provider_status == AMOUNT_MISMATCH


@pytest.mark.asyncio
async def test_confirmed_on_expired_payment_still_counts_real_money() -> None:
    payment, application, db = _linked(status=PaymentStatus.EXPIRED)
    assert await _apply(db, payment, "CONFIRMED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value


@pytest.mark.asyncio
async def test_confirmed_when_application_no_longer_waits_alerts_admin() -> None:
    payment, application, db = _linked(status=PaymentStatus.CANCELLED, app_status=ApplicationStatus.PAID)
    assert await _apply(db, payment, "CONFIRMED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    [alert] = db.events(NotificationAudience.ADMIN)
    assert "возврат" in alert.message
    assert not db.events(NotificationAudience.CLIENT)


# ============================================================
# DEMO-терминал: тестовые деньги не оплачивают настоящую заявку
# ============================================================


@pytest.mark.asyncio
async def test_demo_payment_initiated_by_stranger_does_not_pay_application(monkeypatch) -> None:
    monkeypatch.setattr(tbank_payments.settings, "tbank_test_payer_emails", "tester@example.com")
    stranger = _user(email="client@example.com")
    payment, application, db = _linked(
        provider_account=DEMO_TERMINAL, initiated_by=stranger.id, users=[stranger]
    )
    assert await _apply(db, payment, "CONFIRMED")
    assert payment.status == PaymentStatus.SUCCEEDED.value  # у банка оплачено — не прячем
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value
    assert db.titles(NotificationAudience.ADMIN) == ["Тестовая оплата по реальной заявке"]
    assert not db.events(NotificationAudience.CLIENT)


@pytest.mark.asyncio
async def test_demo_payment_by_verified_tester_pays_application(monkeypatch) -> None:
    monkeypatch.setattr(tbank_payments.settings, "tbank_test_payer_emails", "Tester@Example.com")
    tester = _user()
    payment, application, db = _linked(
        provider_account=DEMO_TERMINAL, initiated_by=tester.id, users=[tester]
    )
    await _apply(db, payment, "CONFIRMED")
    assert application.status == ApplicationStatus.PAID.value


def test_tester_must_have_verified_email(monkeypatch) -> None:
    # Аккаунт создаётся вместе с заявкой: без подтверждения почты любой занял бы адрес тестировщика.
    monkeypatch.setattr(tbank_payments.settings, "tbank_test_payer_emails", "tester@example.com")
    assert may_use_test_terminal(_user())
    assert not may_use_test_terminal(_user(verified=False))
    assert not may_use_test_terminal(_user(email="other@example.com"))
    assert may_use_test_terminal(_user(role=UserRole.ADMIN, email="boss@example.com", verified=False))
    assert not may_use_test_terminal(None)


# ============================================================
# Отказы и отмены неоплаченной ссылки
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bank", "expected"),
    [
        ("REJECTED", PaymentStatus.FAILED),
        ("ATTEMPTS_EXPIRED", PaymentStatus.FAILED),
        ("DEADLINE_EXPIRED", PaymentStatus.EXPIRED),
        ("CANCELED", PaymentStatus.CANCELLED),
        ("REVERSED", PaymentStatus.CANCELLED),
    ],
)
async def test_unpaid_final_statuses_close_an_open_payment(bank, expected) -> None:
    payment, application, db = _linked()
    assert await _apply(db, payment, bank)
    assert payment.status == expected.value
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
@pytest.mark.parametrize("bank", ["CANCELED", "REVERSED", "DEADLINE_EXPIRED"])
async def test_voided_link_is_closed_as_the_caller_asks(bank) -> None:
    payment, application, db = _linked()
    await _apply(db, payment, bank, amount=None, voided_as=PaymentStatus.EXPIRED)
    assert payment.status == PaymentStatus.EXPIRED.value
    assert not db.events()


@pytest.mark.asyncio
async def test_voided_as_does_not_turn_a_rejection_into_expiry() -> None:
    payment, application, db = _linked()
    await _apply(db, payment, "REJECTED", voided_as=PaymentStatus.EXPIRED)
    assert payment.status == PaymentStatus.FAILED.value


@pytest.mark.asyncio
async def test_rejected_on_paid_payment_is_ignored() -> None:
    payment, application, db = _linked(status=PaymentStatus.SUCCEEDED, app_status=ApplicationStatus.PAID)
    assert not await _apply(db, payment, "REJECTED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert not db.events()


@pytest.mark.asyncio
async def test_unknown_status_changes_nothing() -> None:
    payment, application, db = _linked()
    assert not await _apply(db, payment, "SOMETHING_NEW")
    assert payment.status == PaymentStatus.AWAITING_USER.value


# ============================================================
# Закрытие ссылки, которую покупатель успел оплатить
# ============================================================


@pytest.mark.asyncio
async def test_cancel_that_turned_into_refund_is_recorded_as_paid_and_returned() -> None:
    # Cancel у банка по оплаченному платежу — это возврат.
    payment, application, db = _linked()
    await _apply(db, payment, "REFUNDED", amount=None, voided_as=PaymentStatus.CANCELLED)
    assert payment.status == PaymentStatus.REFUNDED.value
    assert payment.refunded_kopeks == AMOUNT
    assert payment.paid_at is not None
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value  # в работу не уходит
    assert db.titles(NotificationAudience.ADMIN) == ["Покупатель оплатил в момент отмены"]
    assert db.titles(NotificationAudience.CLIENT) == ["Оплата отменена"]

    # Более ранний CONFIRMED этой оплаты больше ничего не делает.
    assert not await _apply(db, payment, "CONFIRMED")
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_cancel_that_turned_into_async_refund_finishes_normally() -> None:
    payment, application, db = _linked()
    await _apply(db, payment, "ASYNC_REFUNDING", amount=None, voided_as=PaymentStatus.CANCELLED)
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    assert payment.refund_key is None  # возврат не нашей кнопкой — повторять нечего
    assert await _apply(db, payment, "REFUNDED")
    assert payment.status == PaymentStatus.REFUNDED.value
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_refund_of_paid_at_close_rejected_means_money_stays_and_application_is_paid() -> None:
    # Возврат при закрытии ссылки не прошёл: деньги у магазина — заявка оплачена.
    payment, application, db = _linked()
    await _apply(db, payment, "ASYNC_REFUNDING", amount=None, voided_as=PaymentStatus.CANCELLED)
    assert await _apply(db, payment, "REJECTED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
    assert "Возврат не прошёл" in db.titles(NotificationAudience.ADMIN)


# ============================================================
# Возвраты нашей кнопкой (только полный)
# ============================================================


def _refunding(attempts=1):
    return _linked(
        status=PaymentStatus.REFUND_REQUESTED, app_status=ApplicationStatus.PAID,
        refund_attempts=attempts, refund_key=f"refund:x:{attempts}",
    )


@pytest.mark.asyncio
async def test_full_refund_is_counted_only_when_bank_confirms() -> None:
    payment, application, db = _refunding()
    assert await _apply(db, payment, "REFUNDED")
    assert payment.status == PaymentStatus.REFUNDED.value
    assert payment.refunded_kopeks == AMOUNT
    assert payment.refund_key is None
    assert payment.refunded_at is not None
    [client] = db.events(NotificationAudience.CLIENT)
    assert "1500.00 ₽" in client.message


@pytest.mark.asyncio
async def test_rejected_refund_frees_the_key_for_a_new_attempt() -> None:
    payment, application, db = _refunding()
    assert await _apply(db, payment, "REJECTED")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.refund_key is None  # следующая попытка — с новым ключом
    assert payment.refunded_kopeks == 0
    assert db.titles(NotificationAudience.ADMIN) == ["Возврат не прошёл"]


@pytest.mark.asyncio
async def test_confirmed_during_refund_is_ambiguous_and_waits() -> None:
    # Банк ещё показывает оплату: то ли возврат не начался, то ли не дошёл.
    # Не объявляем отказ — повтор тем же ключом безопасен.
    payment, application, db = _refunding()
    assert not await _apply(db, payment, "CONFIRMED")
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    assert payment.refund_key == "refund:x:1"


@pytest.mark.asyncio
async def test_refunding_during_our_refund_only_updates_provider_status() -> None:
    payment, application, db = _refunding()
    assert not await _apply(db, payment, "ASYNC_REFUNDING")
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    assert payment.provider_status == "ASYNC_REFUNDING"


@pytest.mark.asyncio
async def test_refund_started_from_bank_cabinet_is_tracked() -> None:
    payment, application, db = _linked(status=PaymentStatus.SUCCEEDED, app_status=ApplicationStatus.PAID)
    assert await _apply(db, payment, "ASYNC_REFUNDING")
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    assert payment.refund_key is None


@pytest.mark.asyncio
async def test_full_refund_from_cabinet_without_our_request() -> None:
    payment, application, db = _linked(status=PaymentStatus.SUCCEEDED, app_status=ApplicationStatus.PAID)
    assert await _apply(db, payment, "REFUNDED")
    assert payment.status == PaymentStatus.REFUNDED.value
    assert payment.refunded_kopeks == AMOUNT


@pytest.mark.asyncio
async def test_partial_refund_from_cabinet_asks_admin_to_reconcile_once() -> None:
    payment, application, db = _linked(status=PaymentStatus.SUCCEEDED, app_status=ApplicationStatus.PAID)
    assert await _apply(db, payment, "PARTIAL_REFUNDED")
    assert not await _apply(db, payment, "PARTIAL_REFUNDED")  # повтор — без второго алерта
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.refunded_kopeks == 0  # сумму не выдумываем
    assert db.titles(NotificationAudience.ADMIN) == ["Частичный возврат в ЛК Т-Бизнеса"]


@pytest.mark.asyncio
async def test_refund_failed_helper_keeps_paid_application_as_is() -> None:
    payment, application, db = _refunding()
    await refund_failed(db, payment, reason="Т-Банк отказал в возврате")
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
    assert db.titles(NotificationAudience.CLIENT) == []


# ============================================================
# Идемпотентность, отпечаток и хранение
# ============================================================


def test_event_id_distinguishes_statuses_of_one_payment() -> None:
    authorized = {"PaymentId": 1, "Status": "AUTHORIZED", "Amount": AMOUNT}
    confirmed = {"PaymentId": 1, "Status": "CONFIRMED", "Amount": AMOUNT}
    assert notification_event_id(authorized) != notification_event_id(confirmed)


def test_event_id_is_stable_for_a_bank_retry() -> None:
    body = {"PaymentId": 1, "Status": "CONFIRMED", "Amount": AMOUNT, "Token": "t"}
    retry = dict(reversed(list(body.items())))
    assert notification_event_id(body) == notification_event_id(retry)


def test_fingerprint_sees_every_field_the_automaton_changes() -> None:
    payment = _payment()
    before = fingerprint(payment)
    for field, value in [
        ("status", PaymentStatus.SUCCEEDED.value),
        ("provider_status", "CONFIRMED"),
        ("refunded_kopeks", 1),
        ("refund_attempts", 1),
        ("refund_key", "refund:x:1"),
    ]:
        changed = _payment()
        changed.status, changed.provider_status = payment.status, payment.provider_status
        setattr(changed, field, value)
        assert fingerprint(changed) != before, field


def test_card_expiry_is_not_stored() -> None:
    stored = sanitize_for_storage({"Pan": "430000******0777", "ExpDate": "1129", "Status": "CONFIRMED"})
    assert "ExpDate" not in stored
    assert stored["Pan"] == "430000******0777"
