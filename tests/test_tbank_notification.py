"""Приёмник уведомлений Т-Банка.

Уведомление — только сигнал: решает состояние, которое отдаёт GetState. Тело
проверяется подписью (дешёвый фильтр мусора), но в решения не попадает.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.enums import ApplicationStatus, PaymentProvider, PaymentStatus
from app.models.application import Application
from app.models.payment import Payment
from app.routers import webhooks as webhooks_router
from app.services.dadata import CircuitBreaker
from app.services.tbank_acquiring import (
    TBankClient,
    TBankError,
    TBankService,
    TBankState,
    make_token,
)

TERMINAL = "1000000000001"
PASSWORD = "test-password"
AMOUNT = 150_000
BANK_ID = "9287980194"


class _FakeBank(TBankService):
    """Настоящая проверка подписи + состояние платежа, которое «знает банк»."""

    def __init__(self):
        client = TBankClient(terminal_key=TERMINAL, password=PASSWORD, base_url="https://x/v2", timeout=1)
        super().__init__(client, CircuitBreaker(failure_threshold=3, recovery_seconds=30))
        self.status = "CONFIRMED"
        self.amount = AMOUNT
        self.order_id: str | None = None
        self.fail = False
        self.asked: list[str] = []

    async def get_state(self, *, payment_id: str) -> TBankState:
        self.asked.append(payment_id)
        if self.fail:
            raise TBankError("Т-Банк недоступен (GetState): timeout")
        return TBankState(
            payment_id=payment_id, status=self.status, amount_kopeks=self.amount,
            order_id=self.order_id,
        )


def _request(body: dict | None = None, raw: bytes | None = None) -> Request:
    data = raw if raw is not None else json.dumps(body).encode("utf-8")

    async def receive():
        return {"type": "http.request", "body": data, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)


def _payment() -> Payment:
    p = Payment(
        application_id=uuid4(),
        provider=PaymentProvider.TBANK.value,
        payer_type="individual",
        status=PaymentStatus.AWAITING_USER.value,
        amount_kopeks=AMOUNT,
        currency="RUR",
        pay_for="Юр. адрес: Тест",
        provider_payment_id=BANK_ID,
        provider_account=TERMINAL,
        refunded_kopeks=0,
        refund_attempts=0,
    )
    p.id = uuid4()
    p.created_at = datetime.now(timezone.utc)
    return p


def _signed(payment: Payment, **overrides) -> dict:
    body = {
        "TerminalKey": TERMINAL,
        "OrderId": str(payment.id),
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": int(BANK_ID),
        "ErrorCode": "0",
        "Amount": AMOUNT,
        "Pan": "+7 (912) ***-**-67",  # у СБП в Pan телефон, CardId/ExpDate нет
        "ExpDate": "1129",
    }
    body.update(overrides)
    body["Token"] = make_token(body, PASSWORD)
    return body


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, application):
        self._application = application
        self.added: list = []
        self.commits = 0
        self.rollbacks = 0

    async def get(self, _model, key):
        return self._application if self._application.id == key else None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity") if hasattr(stmt, "column_descriptions") else None
        if entity is Application:
            return _Result(self._application)
        raise RuntimeError("no subscriptions in unit tests")

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def env(monkeypatch):
    payment = _payment()
    application = SimpleNamespace(id=payment.application_id, status=ApplicationStatus.AWAITING_PAYMENT.value)
    bank = _FakeBank()
    state = SimpleNamespace(
        payment=payment, application=application, db=_FakeDB(application), bank=bank,
        stored=[], seen=set(), replay=False, found=payment, lookups=[],
    )
    monkeypatch.setattr(webhooks_router, "get_tbank_service", lambda: bank)

    async def fake_find(_db, *, provider_payment_id, order_id):
        state.lookups.append((provider_payment_id, order_id))
        return state.found

    async def fake_lock(_db, payment_id, *, skip_locked=False):
        return state.found if state.found is not None and state.found.id == payment_id else None

    async def fake_already(_db, *, provider, external_id):
        return external_id in state.seen

    async def fake_store(_db, *, provider, external_id, event_type, body):
        state.stored.append({"provider": provider, "id": external_id, "type": event_type, "body": body})
        return not state.replay

    monkeypatch.setattr(webhooks_router, "find_payment_for_notification", fake_find)
    monkeypatch.setattr(webhooks_router, "lock_payment", fake_lock)
    monkeypatch.setattr(webhooks_router, "_already_stored", fake_already)
    monkeypatch.setattr(webhooks_router, "_store_idempotent", fake_store)
    return state


async def _post(env, body=None, raw=None):
    return await webhooks_router.tbank_notification(request=_request(body, raw), db=env.db)


# ============================================================
# Основной путь
# ============================================================


@pytest.mark.asyncio
async def test_confirmed_by_bank_pays_the_application(env) -> None:
    response = await _post(env, _signed(env.payment))
    assert response.status_code == 200
    assert response.body == b"OK"  # латиница, без JSON и тегов
    assert response.media_type == "text/plain"
    assert env.bank.asked == [BANK_ID]
    assert env.payment.status == PaymentStatus.SUCCEEDED.value
    assert env.payment.provider_checked_at is not None
    assert env.application.status == ApplicationStatus.PAID.value
    assert env.db.commits == 1
    assert env.lookups == [(BANK_ID, str(env.payment.id))]


@pytest.mark.asyncio
async def test_body_does_not_decide_bank_state_does(env) -> None:
    # Подписанное «CONFIRMED», а банк говорит, что покупатель ещё на форме.
    env.bank.status = "FORM_SHOWED"
    await _post(env, _signed(env.payment))
    assert env.payment.status == PaymentStatus.AWAITING_USER.value
    assert env.payment.provider_status == "FORM_SHOWED"
    assert env.application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_amount_is_taken_from_bank_not_from_body(env) -> None:
    env.bank.amount = 100  # тело говорит AMOUNT — верим банку
    await _post(env, _signed(env.payment))
    assert env.payment.status == PaymentStatus.AWAITING_USER.value
    assert env.application.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_sbp_rejection_fails_the_payment(env) -> None:
    env.bank.status = "REJECTED"
    response = await _post(env, _signed(env.payment, Status="REJECTED", Success=True, ErrorCode="0"))
    assert response.body == b"OK"
    assert env.payment.status == PaymentStatus.FAILED.value
    assert env.application.status == ApplicationStatus.AWAITING_PAYMENT.value


# ============================================================
# Подпись, терминал, мусор
# ============================================================


@pytest.mark.asyncio
async def test_bad_signature_is_rejected_before_asking_the_bank(env) -> None:
    body = _signed(env.payment)
    body["Amount"] = 1  # подменили сумму, подпись не пересчитали
    with pytest.raises(HTTPException) as exc:
        await _post(env, body)
    assert exc.value.status_code == 403
    assert env.bank.asked == []
    assert env.stored == []


@pytest.mark.asyncio
async def test_foreign_terminal_is_rejected(env) -> None:
    with pytest.raises(HTTPException) as exc:
        await _post(env, _signed(env.payment, TerminalKey="OTHERDEMO"))
    assert exc.value.status_code == 403
    assert env.bank.asked == []


@pytest.mark.asyncio
async def test_non_ascii_token_is_a_403_not_a_500(env) -> None:
    body = _signed(env.payment)
    body["Token"] = "подпись"
    with pytest.raises(HTTPException) as exc:
        await _post(env, body)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_lone_surrogate_in_body_is_a_403_not_a_500(env) -> None:
    raw = json.dumps(_signed(env.payment)).replace('"CONFIRMED"', '"\\ud800"').encode("ascii")
    with pytest.raises(HTTPException) as exc:
        await _post(env, raw=raw)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b"not json", b"\xff\xfe", b"[1, 2]"])
async def test_garbage_body_is_a_4xx(env, raw) -> None:
    with pytest.raises(HTTPException) as exc:
        await _post(env, raw=raw)
    assert 400 <= exc.value.status_code < 500


@pytest.mark.asyncio
async def test_not_configured_returns_503(monkeypatch, env) -> None:
    from app.services.tbank_acquiring import TBankNotConfigured

    def boom():
        raise TBankNotConfigured("нет ключей")

    monkeypatch.setattr(webhooks_router, "get_tbank_service", boom)
    with pytest.raises(HTTPException) as exc:
        await _post(env, _signed(env.payment))
    assert exc.value.status_code == 503


# ============================================================
# Подделки, которые проходят подпись (ревизия)
# ============================================================


@pytest.mark.asyncio
async def test_boundary_shift_forgery_cannot_fake_a_refund(env) -> None:
    # Подпись склеивает значения без разделителей: PaymentId="…PARTIAL_" +
    # Status="REFUNDED" подписан так же, как PaymentId="…" + Status="PARTIAL_REFUNDED".
    env.payment.status = PaymentStatus.SUCCEEDED.value
    env.application.status = ApplicationStatus.PAID.value
    genuine = _signed(env.payment, Status="PARTIAL_REFUNDED")
    forged = dict(genuine, PaymentId=f"{BANK_ID}PARTIAL_", Status="REFUNDED")
    assert forged["Token"] == make_token(forged, PASSWORD)  # подделка проходит подпись
    env.bank.status = "CONFIRMED"  # а у банка никакого возврата нет
    response = await _post(env, forged)
    assert response.body == b"OK"
    assert env.lookups == [(None, str(env.payment.id))]  # «PaymentId» с буквами отброшен
    assert env.bank.asked == [BANK_ID]  # спросили про НАШ PaymentId
    assert env.payment.status == PaymentStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_payment_id_from_body_must_belong_to_this_order(env) -> None:
    # Init не успел сохранить PaymentId — берём его из тела, но банк должен
    # подтвердить, что это платёж этого заказа (иначе цифры из Pan, сдвинутые в
    # PaymentId, подставили бы состояние другого нашего платежа).
    env.payment.provider_payment_id = None
    env.bank.order_id = str(uuid4())  # банк: это платёж другого заказа
    response = await _post(env, _signed(env.payment))
    assert response.body == b"OK"
    assert env.payment.status == PaymentStatus.AWAITING_USER.value
    assert env.payment.provider_payment_id is None
    assert [r["type"] for r in env.stored] == ["order_mismatch:CONFIRMED"]


@pytest.mark.asyncio
async def test_payment_id_from_body_confirmed_by_bank_is_saved(env) -> None:
    env.payment.provider_payment_id = None
    env.bank.order_id = str(env.payment.id)
    await _post(env, _signed(env.payment))
    assert env.payment.provider_payment_id == BANK_ID
    assert env.payment.status == PaymentStatus.SUCCEEDED.value


# ============================================================
# Повторы, журнал, сбои банка
# ============================================================


@pytest.mark.asyncio
async def test_replay_answers_ok_without_asking_the_bank(env) -> None:
    body = _signed(env.payment)
    env.seen.add(webhooks_router.notification_event_id(body))
    response = await _post(env, body)
    assert response.body == b"OK"
    assert env.bank.asked == []
    assert env.payment.status == PaymentStatus.AWAITING_USER.value
    assert env.db.commits == 0


@pytest.mark.asyncio
async def test_parallel_replay_that_lost_the_race_does_not_commit(env) -> None:
    env.replay = True  # запись в журнал упёрлась в уникальный ключ
    response = await _post(env, _signed(env.payment))
    assert response.body == b"OK"
    assert env.db.commits == 0


@pytest.mark.asyncio
async def test_bank_unavailable_is_503_so_the_bank_retries(env) -> None:
    env.bank.fail = True
    with pytest.raises(HTTPException) as exc:
        await _post(env, _signed(env.payment))
    assert exc.value.status_code == 503
    assert env.stored == []  # не записано — повтор обработается заново
    assert env.db.commits == 0
    assert env.payment.status == PaymentStatus.AWAITING_USER.value


@pytest.mark.asyncio
async def test_unknown_payment_answers_ok_and_is_logged(env) -> None:
    env.found = None
    response = await _post(env, _signed(env.payment))
    assert response.body == b"OK"  # иначе банк будет повторять месяц
    assert env.bank.asked == []
    [record] = env.stored
    assert record["type"] == "unknown:CONFIRMED"


@pytest.mark.asyncio
async def test_fiscal_notification_is_stored_but_does_not_touch_payment(env) -> None:
    response = await _post(env, _signed(env.payment, Status="RECEIPT"))
    assert response.body == b"OK"
    assert env.bank.asked == []
    assert env.payment.status == PaymentStatus.AWAITING_USER.value
    [record] = env.stored
    assert record["type"] == "RECEIPT"


@pytest.mark.asyncio
async def test_card_expiry_never_reaches_storage(env) -> None:
    await _post(env, _signed(env.payment))
    assert env.stored and all("ExpDate" not in r["body"] for r in env.stored)
    assert "ExpDate" not in (env.payment.last_callback_payload or {})
