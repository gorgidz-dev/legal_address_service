"""Роутер платежей с провайдером Т-Банк: создание, просроченные ссылки, сверка, отмена, возврат.

Все решения о деньгах — по состоянию банка (GetState / ответ Cancel) и под
блокировкой строки платежа. Часть сценариев — из адверсариальных ревизий.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, PaymentProvider, PaymentStatus, UserRole
from app.models.address import Address
from app.models.application import Application
from app.models.payment import Payment
from app.routers import payments as payments_router
from app.schemas.payment import PaymentInitiateRequest, PaymentRefundRequest
from app.services import tbank_payments
from app.services.tbank_acquiring import (
    TBankCancelResult,
    TBankError,
    TBankInitResult,
    TBankNotConfigured,
    TBankState,
)

AMOUNT = 2_500_000  # 25 000 ₽ за 11 месяцев
LIVE = "TERMINAL"
DEMO = "TERMINALDEMO"


def _now():
    return datetime.now(timezone.utc)


def _address():
    a = Address(
        full_address="г. Москва, ул. Тверская, 1",
        cadastral_number="77:01:0001001:1234",
        ownership_doc="ЕГРН",
        ownership_doc_short="ЕГРН",
        price_6m=Decimal("15000.00"),
        price_11m=Decimal("25000.00"),
        provider_id=uuid4(),
    )
    a.id = uuid4()
    a.correspondence_price = None
    return a


def _application(address, *, created_by, status=ApplicationStatus.AWAITING_PAYMENT):
    app = Application(
        type="initial_registration",
        status=status.value,
        provider_id=address.provider_id,
        address_id=address.id,
        company_name="Альфа",
        contact_name="Иван Иванов",
        contact_phone="+79001234567",
        contact_email="ivan@example.ru",
        term_months=11,
        has_correspondence_service=False,
        created_by=created_by,
    )
    app.id = uuid4()
    return app


def _user(role=UserRole.CLIENT, email="client@example.ru", verified=True):
    return SimpleNamespace(
        id=uuid4(), email=email, role=role.value, is_active=True,
        email_verified_at=_now() if verified else None,
    )


ADMIN = _user(role=UserRole.ADMIN, email="admin@uradres.net")


def _tbank_payment(application, *, status=PaymentStatus.AWAITING_USER, age=timedelta(0), **kw):
    p = Payment(
        application_id=application.id,
        provider=PaymentProvider.TBANK.value,
        payer_type="individual",
        status=status.value,
        amount_kopeks=AMOUNT,
        currency="RUR",
        pay_for="Юр. адрес: Альфа",
        provider_payment_id=kw.pop("provider_payment_id", "111"),
        provider_account=kw.pop("provider_account", LIVE),
        payment_url="https://pay.tbank.ru/new/old",
        refunded_kopeks=kw.pop("refunded_kopeks", 0),
        refund_attempts=kw.pop("refund_attempts", 0),
        **kw,
    )
    p.id = uuid4()
    p.created_at = _now() - age
    p.updated_at = p.created_at
    return p


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *, address=None, application=None, payment=None, users=()):
        self._address, self._application, self._payment = address, application, payment
        self._users = {u.id: u for u in users}
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model, key):
        for obj, cls in ((self._application, Application), (self._address, Address), (self._payment, Payment)):
            if model is cls and obj is not None and obj.id == key:
                return obj
        return self._users.get(key)

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity") if hasattr(stmt, "column_descriptions") else None
        if entity is Application:  # _lock_application в автомате
            return _Result(self._application)
        raise RuntimeError("no subscriptions in unit tests")  # dispatch_event внутри событий

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "created_at", None) is None:
                item.created_at = _now()
                item.updated_at = _now()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _item):
        pass

    def new_payments(self) -> list[Payment]:
        return [x for x in self.added if isinstance(x, Payment)]


class _FakeTBank:
    def __init__(self, *, is_demo=False, state="NEW", state_amount=AMOUNT,
                 init_error=None, state_error=None, cancel_status="CANCELED",
                 cancel_error=None, state_after_cancel=None):
        self.is_demo = is_demo
        self.terminal_key = DEMO if is_demo else LIVE
        self.state, self.state_amount = state, state_amount
        self.init_error, self.state_error, self.cancel_error = init_error, state_error, cancel_error
        self.cancel_status = cancel_status
        self.state_after_cancel = state_after_cancel
        self.calls: list[tuple[str, dict]] = []

    async def init(self, **kw):
        self.calls.append(("init", kw))
        if self.init_error:
            raise self.init_error
        return TBankInitResult(payment_id="555", payment_url="https://pay.tbank.ru/new/fresh", status="NEW")

    async def get_state(self, *, payment_id):
        self.calls.append(("get_state", {"payment_id": payment_id}))
        if self.state_error:
            raise self.state_error
        cancelled = any(name == "cancel" for name, _ in self.calls)
        status = self.state_after_cancel if (cancelled and self.state_after_cancel) else self.state
        return TBankState(payment_id=payment_id, status=status, amount_kopeks=self.state_amount)

    async def cancel(self, **kw):
        self.calls.append(("cancel", kw))
        if self.cancel_error:
            raise self.cancel_error
        return TBankCancelResult(status=self.cancel_status, original_amount_kopeks=AMOUNT, new_amount_kopeks=0)

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


@pytest.fixture
def tbank(monkeypatch):
    """Провайдер Т-Банк включён; поиск активного платежа, блокировки и слот сверки — подменяемые."""
    monkeypatch.setattr(payments_router.settings, "payment_provider", "tbank")
    monkeypatch.setattr(payments_router.settings, "tbank_test_payer_emails", "tester@uradres.net")
    state = SimpleNamespace(service=_FakeTBank(), active=None, claim=True, claims=0, on_lock=None, locks=[])

    def service():
        if state.service is None:
            raise TBankNotConfigured("нет ключей")
        return state.service

    async def fake_find(_db, _application_id):
        return state.active

    async def fake_lock(db, payment_id, *, skip_locked=False):
        state.locks.append(skip_locked)
        payment = await db.get(Payment, payment_id)
        if state.on_lock is not None and payment is not None:
            state.on_lock(payment)  # «пока ходили в банк, платёж изменил другой запрос»
        return payment

    async def fake_claim(_db, _payment_id, _now):
        state.claims += 1
        return state.claim

    for module in (payments_router, tbank_payments):
        monkeypatch.setattr(module, "get_tbank_service", service)
        monkeypatch.setattr(module, "lock_payment", fake_lock)
    monkeypatch.setattr(payments_router, "_find_active_payment", fake_find)
    monkeypatch.setattr(tbank_payments, "claim_recheck_slot", fake_claim)
    return state


def _setup(active_payment=None, *, app_status=ApplicationStatus.AWAITING_PAYMENT, user=None):
    address = _address()
    user = user or _user()
    application = _application(address, created_by=user.id, status=app_status)
    payment = active_payment(application) if callable(active_payment) else None
    if payment is not None and payment.initiated_by is None:
        payment.initiated_by = user.id
    db = _FakeDB(address=address, application=application, payment=payment, users=[user, ADMIN])
    return db, application, payment, user


async def _initiate(db, application, user):
    return await payments_router.initiate_payment(
        payload=PaymentInitiateRequest(application_id=application.id), db=db, user=user
    )


def _expired(days=1, **kw):
    return lambda app: _tbank_payment(
        app, age=timedelta(days=days + 1), expires_at=_now() - timedelta(days=days), **kw
    )


# ============================================================
# Создание платежа
# ============================================================


@pytest.mark.asyncio
async def test_initiate_creates_tbank_payment(tbank) -> None:
    db, application, _, user = _setup()
    result = await _initiate(db, application, user)

    assert result.provider == PaymentProvider.TBANK.value
    assert result.status == PaymentStatus.AWAITING_USER.value
    assert result.amount_kopeks == AMOUNT
    assert result.currency == "RUR"
    assert result.provider_payment_id == "555"
    assert result.provider_account == LIVE  # терминал запомнен — смена ключа не потеряет платёж
    assert result.payment_url == "https://pay.tbank.ru/new/fresh"
    assert result.expires_at is not None
    [(name, kw)] = tbank.service.calls
    assert name == "init"
    assert kw["order_id"] == str(result.id)  # OrderId = наш id — по нему найдём платёж
    assert kw["amount_kopeks"] == AMOUNT
    assert kw["notification_url"].endswith("/api/v1/webhooks/tbank/notification")
    # Возврат — на страницу фронта с id заявки (frontend/src/payment/PaymentReturnPage.tsx).
    assert kw["success_url"].endswith(f"/payment/success?application={application.id}")
    assert kw["fail_url"].endswith(f"/payment/fail?application={application.id}")


def test_return_urls_can_be_overridden(monkeypatch) -> None:
    monkeypatch.setattr(payments_router.settings, "tbank_success_url", "https://x.test/ok")
    monkeypatch.setattr(payments_router.settings, "tbank_fail_url", "")
    app_id = uuid4()
    assert payments_router._tbank_return_url("success", app_id) == "https://x.test/ok"
    assert payments_router._tbank_return_url("fail", app_id).endswith(f"/payment/fail?application={app_id}")


def test_return_page_route_exists_in_frontend_router() -> None:
    # Бэкенд строит адрес /payment/<result>, фронт обязан его разбирать.
    from pathlib import Path

    router_ts = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "router.ts").read_text(encoding="utf-8")
    assert 'head === "payment"' in router_ts


@pytest.mark.asyncio
async def test_demo_terminal_refuses_real_clients(tbank) -> None:
    tbank.service = _FakeTBank(is_demo=True)
    db, application, _, user = _setup()
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 403
    assert tbank.service.calls == []
    assert db.new_payments() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "who",
    [_user(email="Tester@Uradres.net"), _user(role=UserRole.ADMIN, email="admin@uradres.net")],
)
async def test_demo_terminal_lets_testers_and_admins_pay(tbank, who) -> None:
    tbank.service = _FakeTBank(is_demo=True)
    db, application, _, _ = _setup(user=who)
    result = await _initiate(db, application, who)
    assert result.status == PaymentStatus.AWAITING_USER.value
    assert result.payment_url == "https://pay.tbank.ru/new/fresh"


@pytest.mark.asyncio
async def test_unverified_tester_email_cannot_pay_on_demo(tbank) -> None:
    # Аккаунт с адресом тестировщика создаётся вместе с заявкой — без подтверждения.
    tbank.service = _FakeTBank(is_demo=True)
    impostor = _user(email="tester@uradres.net", verified=False)
    db, application, _, _ = _setup(user=impostor)
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, impostor)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_init_error_marks_payment_failed(tbank) -> None:
    tbank.service = _FakeTBank(init_error=TBankError("Неверные параметры", error_code="201"))
    db, application, _, user = _setup()
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 502
    assert "код 201" in exc.value.detail and "поддержку" in exc.value.detail
    [payment] = db.new_payments()
    assert payment.status == PaymentStatus.FAILED.value
    assert payment.provider_status == "INIT_ERROR:201"
    assert db.commits == 1  # провал сохранён, а не потерян


@pytest.mark.asyncio
async def test_init_network_error_shows_buyer_a_plain_message(tbank) -> None:
    # Найдено проверкой в браузере: покупатель видел «Т-Банк недоступен (Init):».
    tbank.service = _FakeTBank(init_error=TBankError("Т-Банк недоступен (Init): ConnectTimeout"))
    db, application, _, user = _setup()
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 502
    assert exc.value.detail == "Банк сейчас не отвечает. Попробуйте ещё раз через минуту."


@pytest.mark.asyncio
async def test_live_link_is_returned_again(tbank) -> None:
    db, application, payment, user = _setup(lambda app: _tbank_payment(app, expires_at=_now() + timedelta(hours=5)))
    tbank.active = payment
    result = await _initiate(db, application, user)
    assert result is payment
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_existing_demo_link_is_not_handed_to_a_real_client(tbank) -> None:
    # Ссылку создал админ, а оплатить тестовой картой хочет владелец заявки.
    tbank.service = _FakeTBank(is_demo=True)
    db, application, payment, user = _setup(
        lambda app: _tbank_payment(app, provider_account=DEMO, expires_at=_now() + timedelta(hours=5))
    )
    tbank.active = payment
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_demo_link_is_masked_when_terminal_is_switched_off(tbank) -> None:
    # Терминал отключён — гард не сработает, но DEMO-ссылку клиент всё равно не увидит.
    tbank.service = None
    db, application, payment, user = _setup(
        lambda app: _tbank_payment(app, provider_account=DEMO, expires_at=_now() + timedelta(hours=5))
    )
    tbank.active = payment
    result = await _initiate(db, application, user)
    assert result.payment_url is None
    assert payment.payment_url == "https://pay.tbank.ru/new/old"  # в базе ссылка не тронута


# ============================================================
# Просроченная ссылка: закрыть у банка, потом выдать новую
# ============================================================


@pytest.mark.asyncio
async def test_expired_unpaid_link_is_closed_and_replaced(tbank) -> None:
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="NEW")
    result = await _initiate(db, application, user)

    assert tbank.service.names() == ["get_state", "cancel", "init"]  # закрыть старую, потом новая
    assert old.status == PaymentStatus.EXPIRED.value
    assert result is not old
    assert result.provider_payment_id == "555"


@pytest.mark.asyncio
async def test_expired_link_paid_at_the_last_minute_is_counted(tbank) -> None:
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="CONFIRMED")
    result = await _initiate(db, application, user)

    assert result is old
    assert old.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
    assert "init" not in tbank.service.names()  # второй ссылки нет — второй оплаты не будет


@pytest.mark.asyncio
async def test_expired_link_with_amount_mismatch_is_not_cancelled(tbank) -> None:
    # Банк показывает оплату с чужой суммой: Cancel был бы ВОЗВРАТОМ — решает человек.
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="CONFIRMED", state_amount=100)
    result = await _initiate(db, application, user)
    assert result is old
    assert tbank.service.names() == ["get_state"]
    assert old.status == PaymentStatus.AWAITING_USER.value


@pytest.mark.asyncio
async def test_expired_link_being_paid_right_now_is_not_replaced(tbank) -> None:
    db, application, old, user = _setup(
        lambda app: _tbank_payment(app, age=timedelta(days=1), expires_at=_now() - timedelta(minutes=10))
    )
    tbank.active = old
    tbank.service = _FakeTBank(state="AUTHORIZING")
    result = await _initiate(db, application, user)
    assert result is old
    assert tbank.service.names() == ["get_state"]


@pytest.mark.asyncio
async def test_money_moving_for_hours_after_expiry_is_treated_as_stuck(tbank) -> None:
    db, application, old, user = _setup(
        lambda app: _tbank_payment(app, age=timedelta(days=2), expires_at=_now() - timedelta(hours=3))
    )
    tbank.active = old
    tbank.service = _FakeTBank(state="AUTHORIZED", cancel_status="REVERSED")
    result = await _initiate(db, application, user)
    assert tbank.service.names() == ["get_state", "cancel", "init"]
    assert old.status == PaymentStatus.EXPIRED.value
    assert result is not old


@pytest.mark.asyncio
async def test_link_stuck_in_auth_fail_is_replaced_even_if_bank_refuses_cancel(tbank) -> None:
    # AUTH_FAIL/3DS_CHECKING раньше навсегда блокировали новую ссылку. Денег по
    # ним нет — если банк откажет в Cancel, закрываем у себя.
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="AUTH_FAIL", cancel_error=TBankError("Нельзя", error_code="4"))
    result = await _initiate(db, application, user)
    assert tbank.service.names() == ["get_state", "cancel", "init"]
    assert old.status == PaymentStatus.EXPIRED.value
    assert result.provider_payment_id == "555"


@pytest.mark.asyncio
async def test_unknown_bank_status_blocks_replacement(tbank) -> None:
    # Статус не из справочника: Cancel мог бы оказаться возвратом — не рискуем.
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="SOMETHING_NEW")
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 409
    assert tbank.service.names() == ["get_state"]


@pytest.mark.asyncio
async def test_expired_link_bank_unreachable_gives_502_not_a_second_link(tbank) -> None:
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state_error=TBankError("нет сети"))
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 502
    assert "init" not in tbank.service.names()


@pytest.mark.asyncio
async def test_cancel_lost_in_network_is_rechecked_and_no_second_link(tbank) -> None:
    # Cancel ушёл, ответ потерялся: уточняем GetState — ссылку уже закрыли.
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="NEW", cancel_error=TBankError("таймаут"), state_after_cancel="CANCELED")
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 502
    assert old.status == PaymentStatus.EXPIRED.value  # итог записан — повтор выдаст новую
    assert "init" not in tbank.service.names()


@pytest.mark.asyncio
async def test_replacing_link_paid_at_the_last_second_records_refund(tbank) -> None:
    # GetState сказал NEW, а к моменту Cancel покупатель заплатил — Cancel у
    # банка стал возвратом. Платёж «оплачен и возвращается», заявка ждёт.
    db, application, old, user = _setup(_expired())
    tbank.active = old
    tbank.service = _FakeTBank(state="NEW", cancel_status="REFUNDED")
    await _initiate(db, application, user)
    assert old.status == PaymentStatus.REFUNDED.value
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_stuck_pending_without_bank_id_is_replaced_without_asking_bank(tbank) -> None:
    db, application, old, user = _setup(
        lambda app: _tbank_payment(
            app, status=PaymentStatus.PENDING, age=timedelta(minutes=30), provider_payment_id=None
        )
    )
    tbank.active = old
    result = await _initiate(db, application, user)
    assert old.status == PaymentStatus.EXPIRED.value
    assert tbank.service.names() == ["init"]
    assert result.provider_payment_id == "555"


@pytest.mark.asyncio
async def test_link_already_retired_by_parallel_request_is_not_touched(tbank) -> None:
    db, application, old, user = _setup(_expired())
    tbank.active = old

    def parallel_retired(p):
        p.status = PaymentStatus.EXPIRED.value

    tbank.on_lock = parallel_retired
    await _initiate(db, application, user)
    assert "get_state" not in tbank.service.names()
    assert "cancel" not in tbank.service.names()


@pytest.mark.asyncio
async def test_foreign_demo_terminal_payment_is_retired_without_asking_the_bank(tbank) -> None:
    # После смены DEMO на боевой старый платёж текущему терминалу неизвестен.
    db, application, old, user = _setup(
        lambda app: _tbank_payment(app, provider_account="OLDTERMINALDEMO", expires_at=_now() + timedelta(hours=5))
    )
    tbank.active = old
    result = await _initiate(db, application, user)
    assert tbank.service.names() == ["init"]
    assert old.status == PaymentStatus.EXPIRED.value
    assert result.provider_payment_id == "555"


@pytest.mark.asyncio
async def test_foreign_live_terminal_payment_is_never_closed_silently(tbank) -> None:
    # Ссылка боевого терминала жива и оплачиваема, а уведомления мы больше не
    # примем: молча закрыть = потерять настоящие деньги.
    db, application, old, user = _setup(
        lambda app: _tbank_payment(app, provider_account="OLDLIVE", expires_at=_now() + timedelta(hours=5))
    )
    tbank.active = old
    with pytest.raises(HTTPException) as exc:
        await _initiate(db, application, user)
    assert exc.value.status_code == 409
    assert old.status == PaymentStatus.AWAITING_USER.value
    assert tbank.service.calls == []


# ============================================================
# Сверка при чтении платежа
# ============================================================


@pytest.mark.asyncio
async def test_get_payment_rechecks_with_bank_and_applies_confirmation(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, age=timedelta(minutes=5)))
    tbank.service = _FakeTBank(state="CONFIRMED")
    result = await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert result.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
    # Отметку ставит атомарный UPDATE в claim_recheck_slot (в смоуке — на настоящем Postgres).
    assert tbank.claims == 1
    assert tbank.locks == [True]  # SKIP LOCKED: опрос не ждёт чужой возврат/отмену


@pytest.mark.asyncio
async def test_get_payment_does_not_hammer_the_bank(tbank) -> None:
    db, application, payment, _ = _setup(
        lambda app: _tbank_payment(app, age=timedelta(minutes=5), provider_checked_at=_now() - timedelta(seconds=5))
    )
    await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_get_payment_skips_the_first_seconds(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, age=timedelta(seconds=3)))
    await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert tbank.claims == 0


@pytest.mark.asyncio
async def test_get_payment_survives_bank_outage(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, age=timedelta(minutes=5)))
    tbank.service = _FakeTBank(state_error=TBankError("нет сети"))
    result = await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert result.status == PaymentStatus.AWAITING_USER.value


@pytest.mark.asyncio
async def test_recheck_goes_to_bank_only_with_claimed_slot(tbank) -> None:
    # Из N одновременных опросов в банк идёт один.
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, age=timedelta(minutes=5)))
    tbank.claim = False
    await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert tbank.claims == 1
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_recheck_discards_stale_bank_snapshot(tbank) -> None:
    # Пока ходили в банк, платёж изменил другой запрос — старый снимок не применяем.
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, age=timedelta(minutes=5)))
    tbank.service = _FakeTBank(state="REJECTED")

    def notification_won(p):
        p.status = PaymentStatus.SUCCEEDED.value

    tbank.on_lock = notification_won
    result = await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert result.status == PaymentStatus.SUCCEEDED.value  # устаревший REJECTED не применён


@pytest.mark.asyncio
async def test_recheck_tracks_refund_in_progress(tbank) -> None:
    db, application, payment, _ = _setup(
        lambda app: _tbank_payment(
            app, status=PaymentStatus.REFUND_REQUESTED, age=timedelta(days=1),
            refund_attempts=1, refund_key="refund:x:1",
        ),
        app_status=ApplicationStatus.PAID,
    )
    tbank.service = _FakeTBank(state="REFUNDED")
    result = await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert result.status == PaymentStatus.REFUNDED.value
    assert result.refunded_kopeks == AMOUNT


@pytest.mark.asyncio
async def test_demo_link_is_hidden_from_client_who_did_not_create_it(tbank) -> None:
    # Ссылку DEMO выдали админу — владелец заявки через GET её не получит.
    db, application, payment, user = _setup(
        lambda app: _tbank_payment(app, provider_account=DEMO, provider_checked_at=_now())
    )
    result = await payments_router.get_payment(payment_id=payment.id, db=db, user=user)
    assert result.payment_url is None
    admin_view = await payments_router.get_payment(payment_id=payment.id, db=db, user=ADMIN)
    assert admin_view.payment_url == "https://pay.tbank.ru/new/old"


@pytest.mark.asyncio
async def test_demo_link_is_hidden_in_by_application_view(tbank) -> None:
    db, application, payment, user = _setup(lambda app: _tbank_payment(app, provider_account=DEMO))

    async def execute(stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: payment))

    db.execute = execute
    result = await payments_router.get_payment_by_application(application_id=application.id, db=db, user=user)
    assert result.payment_url is None


# ============================================================
# Отмена админом
# ============================================================


async def _cancel(db, payment):
    return await payments_router.cancel_payment(payment_id=payment.id, db=db, _admin=ADMIN)


@pytest.mark.asyncio
async def test_admin_cancel_closes_link_at_bank(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="FORM_SHOWED")
    result = await _cancel(db, payment)
    assert tbank.service.names() == ["get_state", "cancel"]
    assert result.status == PaymentStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_admin_cancel_of_paid_payment_counts_payment_instead(tbank) -> None:
    # Cancel по оплаченному у банка — это возврат. Не отменяем, а засчитываем оплату.
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="CONFIRMED")
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 409
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
    assert "cancel" not in tbank.service.names()
    assert db.commits == 1  # оплата сохранена, несмотря на 409


@pytest.mark.asyncio
async def test_admin_cancel_of_amount_mismatch_is_refused(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="CONFIRMED", state_amount=1)
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 409
    assert "cancel" not in tbank.service.names()


@pytest.mark.asyncio
async def test_admin_cancel_while_customer_pays_is_refused(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="AUTHORIZING")
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 409
    assert "cancel" not in tbank.service.names()


@pytest.mark.asyncio
async def test_admin_cancel_with_unknown_bank_status_is_refused(tbank) -> None:
    # Статус не из справочника: Cancel мог бы оказаться возвратом.
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="SOMETHING_NEW")
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 409
    assert "cancel" not in tbank.service.names()


@pytest.mark.asyncio
async def test_admin_cancel_bank_network_error_keeps_payment_open(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="NEW", cancel_error=TBankError("сбой"))
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 502
    assert payment.status == PaymentStatus.AWAITING_USER.value  # ссылка жива — не врём, что отменено


@pytest.mark.asyncio
async def test_admin_cancel_turned_refund_does_not_pay_the_application(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="FORM_SHOWED", cancel_status="REFUNDED")
    result = await _cancel(db, payment)
    assert result.status == PaymentStatus.REFUNDED.value
    assert application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_admin_cancel_refuses_when_status_changed_meanwhile(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    tbank.service = _FakeTBank(state="NEW")

    def paid_meanwhile(p):
        p.status = PaymentStatus.SUCCEEDED.value

    tbank.on_lock = paid_meanwhile
    with pytest.raises(HTTPException) as exc:
        await _cancel(db, payment)
    assert exc.value.status_code == 409
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_admin_cancel_of_foreign_demo_payment_is_local(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app, provider_account="OLDDEMO"))
    result = await _cancel(db, payment)
    assert result.status == PaymentStatus.CANCELLED.value
    assert tbank.service.calls == []


# ============================================================
# Возврат — только полный, ключ по номеру попытки
# ============================================================


def _paid(app):
    return _tbank_payment(app, status=PaymentStatus.SUCCEEDED, provider_status="CONFIRMED")


async def _refund(db, payment, amount=None):
    return await payments_router.refund_payment(
        payment_id=payment.id,
        payload=PaymentRefundRequest(reason="Возврат", value_refund_kopeks=amount),
        db=db, _admin=ADMIN,
    )


@pytest.mark.asyncio
async def test_full_refund_sends_no_amount_and_closes_payment(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(cancel_status="REFUNDED")
    result = await _refund(db, payment)
    [(name, kw)] = tbank.service.calls
    assert name == "cancel"
    assert "amount_kopeks" not in kw  # полный возврат: банк сам сформирует чек возврата
    assert kw["external_request_id"] == f"refund:{payment.id}:1"
    assert result.status == PaymentStatus.REFUNDED.value
    assert result.refunded_kopeks == AMOUNT
    assert result.refund_key is None


@pytest.mark.asyncio
async def test_refund_with_explicit_full_amount_is_accepted(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(cancel_status="REFUNDED")
    result = await _refund(db, payment, amount=AMOUNT)
    assert result.status == PaymentStatus.REFUNDED.value


@pytest.mark.asyncio
async def test_partial_refund_goes_to_bank_cabinet(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment, amount=500_000)
    assert exc.value.status_code == 422
    assert "ЛК" in exc.value.detail
    assert tbank.service.calls == []
    assert payment.status == PaymentStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_refund_after_partial_refund_in_cabinet_is_refused(tbank) -> None:
    db, application, payment, _ = _setup(
        lambda app: _tbank_payment(app, status=PaymentStatus.SUCCEEDED, provider_status="PARTIAL_REFUNDED"),
        app_status=ApplicationStatus.PAID,
    )
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 409
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_refund_of_unpaid_payment_is_refused(tbank) -> None:
    db, application, payment, _ = _setup(lambda app: _tbank_payment(app))
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_async_refund_stays_in_progress(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(cancel_status="ASYNC_REFUNDING")
    result = await _refund(db, payment)
    assert result.status == PaymentStatus.REFUND_REQUESTED.value
    assert result.refund_key == f"refund:{payment.id}:1"
    assert result.refunded_kopeks == 0  # засчитаем, когда банк скажет REFUNDED


@pytest.mark.asyncio
async def test_refund_final_refusal_is_confirmed_by_get_state(tbank) -> None:
    # Банк отказал, и GetState показывает оплату без возврата — отказ окончательный.
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(state="CONFIRMED", cancel_error=TBankError("Недостаточно средств", error_code="3002"))
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 502
    assert tbank.service.names() == ["cancel", "get_state"]
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.refund_key is None  # следующая попытка — с новым ключом
    assert payment.refunded_kopeks == 0


@pytest.mark.asyncio
async def test_refund_refusal_on_retry_that_already_went_through(tbank) -> None:
    # Повтор отклонён, потому что первая попытка уже идёт — GetState это покажет.
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(state="ASYNC_REFUNDING", cancel_error=TBankError("Уже", error_code="7"))
    result = await _refund(db, payment)
    assert result.status == PaymentStatus.REFUND_REQUESTED.value
    assert result.refund_key == f"refund:{payment.id}:1"


@pytest.mark.asyncio
async def test_refund_refusal_with_unknown_state_is_not_declared_final(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(
        cancel_error=TBankError("Отказ", error_code="3002"), state_error=TBankError("нет сети")
    )
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 502
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    assert payment.refund_key == f"refund:{payment.id}:1"  # повтор — тем же ключом


@pytest.mark.asyncio
async def test_refund_network_failure_keeps_it_in_flight_and_retry_reuses_key(tbank) -> None:
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(cancel_error=TBankError("нет сети"))
    with pytest.raises(HTTPException):
        await _refund(db, payment)
    assert payment.status == PaymentStatus.REFUND_REQUESTED.value
    first_key = tbank.service.calls[-1][1]["external_request_id"]

    tbank.service = _FakeTBank(cancel_status="REFUNDED")
    result = await _refund(db, payment)
    assert tbank.service.calls[-1][1]["external_request_id"] == first_key  # банк не исполнит дважды
    assert result.status == PaymentStatus.REFUNDED.value
    assert result.refunded_kopeks == AMOUNT


@pytest.mark.asyncio
async def test_refund_can_be_repeated_after_bank_rejected_it(tbank) -> None:
    # Возврат → банк отклонил (REJECTED) → повтор идёт НОВЫМ ключом и проходит.
    db, application, payment, _ = _setup(_paid, app_status=ApplicationStatus.PAID)
    tbank.service = _FakeTBank(cancel_status="ASYNC_REFUNDING")
    await _refund(db, payment)
    first_key = tbank.service.calls[-1][1]["external_request_id"]
    await tbank_payments.apply_bank_state(db, payment=payment, status="REJECTED", amount_kopeks=None)
    assert payment.status == PaymentStatus.SUCCEEDED.value

    tbank.service = _FakeTBank(cancel_status="REFUNDED")
    result = await _refund(db, payment)
    assert result.status == PaymentStatus.REFUNDED.value
    assert tbank.service.calls[-1][1]["external_request_id"] == f"refund:{payment.id}:2"
    assert first_key != f"refund:{payment.id}:2"


@pytest.mark.asyncio
async def test_refund_started_elsewhere_cannot_be_pushed_again(tbank) -> None:
    db, application, payment, _ = _setup(
        lambda app: _tbank_payment(app, status=PaymentStatus.REFUND_REQUESTED),  # без refund_key
        app_status=ApplicationStatus.PAID,
    )
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 409
    assert tbank.service.calls == []


@pytest.mark.asyncio
async def test_refund_of_foreign_terminal_payment_is_refused(tbank) -> None:
    db, application, payment, _ = _setup(
        lambda app: _tbank_payment(app, status=PaymentStatus.SUCCEEDED, provider_account="OLDLIVE"),
        app_status=ApplicationStatus.PAID,
    )
    with pytest.raises(HTTPException) as exc:
        await _refund(db, payment)
    assert exc.value.status_code == 409
    assert tbank.service.calls == []


# ============================================================
# Адрес уведомлений
# ============================================================


def test_tbank_notification_url_matches_route() -> None:
    from app.main import API_PREFIX, _is_public_path
    from app.routers.webhooks import router as webhooks_router

    route_paths = {getattr(route, "path", "") for route in webhooks_router.routes}
    assert payments_router.TBANK_NOTIFICATION_PATH in {API_PREFIX + p for p in route_paths}
    # И путь открыт для банка (иначе middleware ответит 401 на каждое уведомление).
    assert _is_public_path(payments_router.TBANK_NOTIFICATION_PATH, "POST")


# ============================================================
# Гонка двух «Оплатить» (сторож ошибки, найденной смоуком на Postgres)
# ============================================================


class _ExpiringApplication:
    """Ведёт себя как ORM-объект после rollback: чтение атрибутов — ошибка.

    Настоящая сессия после rollback помечает объекты устаревшими, и чтение
    application.id полезло бы в базу синхронно — в async это MissingGreenlet.
    Подставная база этого не видит, поэтому имитируем.
    """

    def __init__(self, application, db):
        object.__setattr__(self, "_app", application)
        object.__setattr__(self, "_db", db)

    def __getattr__(self, name):
        if self._db.rollbacks:
            raise AssertionError(f"чтение application.{name} после rollback (MissingGreenlet в проде)")
        return getattr(self._app, name)


async def _double_click(db, tbank, monkeypatch, application):
    from sqlalchemy.exc import IntegrityError

    winner = _tbank_payment(application)
    real_flush = db.flush

    async def flush_hits_unique_index():
        if any(isinstance(x, Payment) for x in db.added):
            tbank.active = winner  # победитель уже закоммичен
            raise IntegrityError("INSERT", {}, Exception("ux_payments_one_active_per_application"))
        await real_flush()

    monkeypatch.setattr(db, "flush", flush_hits_unique_index)
    return winner


@pytest.mark.asyncio
async def test_concurrent_initiate_returns_the_winner_without_touching_expired_objects(tbank, monkeypatch) -> None:
    db, application, _, user = _setup()
    winner = await _double_click(db, tbank, monkeypatch, application)
    result = await payments_router._initiate_tbank(db, _ExpiringApplication(application, db), user)
    assert result is winner
    assert db.rollbacks == 1
    assert tbank.service.calls == []  # проигравший в банк не ходил


@pytest.mark.asyncio
async def test_concurrent_initiate_endpoint_does_not_read_expired_user(tbank, monkeypatch) -> None:
    # Смоук на Postgres: проигравший двойной клик делал rollback, а потом
    # _masked_for читал user.role — MissingGreenlet, 500 вместо ссылки.
    db, application, _, user = _setup()
    winner = await _double_click(db, tbank, monkeypatch, application)
    result = await _initiate(db, application, _ExpiringApplication(user, db))
    assert result is winner


@pytest.mark.asyncio
async def test_cdek_double_click_returns_the_winner(tbank, monkeypatch) -> None:
    monkeypatch.setattr(payments_router.settings, "payment_provider", "cdek_pay")
    monkeypatch.setattr(payments_router, "get_cdek_pay_service", lambda: SimpleNamespace(currency="RUR"))
    db, application, _, user = _setup()
    winner = await _double_click(db, tbank, monkeypatch, application)
    result = await payments_router._initiate_cdek(
        db, _ExpiringApplication(application, db), PaymentInitiateRequest(application_id=application.id), user
    )
    assert result is winner
