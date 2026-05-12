from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, PaymentPayerType, PaymentProvider, PaymentStatus
from app.models.payment import Payment
from app.routers.payments import (
    handle_cdek_pay_payment_callback,
    handle_cdek_pay_refund_callback,
)
from app.services.cdek_pay import sign_payment_order


def _now():
    return datetime.now(timezone.utc)


def _make_payment(*, status: PaymentStatus = PaymentStatus.AWAITING_USER, access_key: str = "ak1"):
    p = Payment(
        application_id=uuid4(),
        provider=PaymentProvider.CDEK_PAY.value,
        payer_type=PaymentPayerType.INDIVIDUAL.value,
        status=status.value,
        amount_kopeks=1500000,
        currency="TST",
        pay_for="Юр. адрес: Тест",
        cdek_access_key=access_key,
        cdek_order_id=123,
    )
    p.id = uuid4()
    p.created_at = _now()
    p.updated_at = _now()
    return p


def _make_application(*, status: ApplicationStatus = ApplicationStatus.AWAITING_PAYMENT):
    return SimpleNamespace(
        id=uuid4(),
        status=status.value,
        created_at=_now(),
        updated_at=_now(),
    )


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *, payment=None, application=None):
        self._payment = payment
        self._application = application
        self.added = []
        self.committed = False

    async def get(self, model, key):
        if self._application is not None and getattr(self._application, "id", None) == key:
            return self._application
        return None

    async def execute(self, _stmt):
        return _FakeResult(self._payment)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "created_at", None) is None:
                item.created_at = _now()
            if getattr(item, "updated_at", None) is None:
                item.updated_at = _now()

    async def commit(self):
        self.committed = True

    async def refresh(self, _item):
        pass


# ============================================================
# payment_success callback
# ============================================================


@pytest.mark.asyncio
async def test_payment_callback_marks_payment_succeeded_and_application_paid() -> None:
    payment = _make_payment()
    application = _make_application()
    payment.application_id = application.id
    db = _FakeDB(payment=payment, application=application)

    body = {
        "payment": {
            "id": 555,
            "order_id": 999,
            "access_key": "ak1",
            "pay_amount": 1500000,
            "currency": "TST",
        },
        "signature": "ignored-by-handler",  # signature already verified in router
    }

    await handle_cdek_pay_payment_callback(db=db, body=body)

    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.cdek_payment_id == 555
    assert payment.paid_at is not None
    assert payment.last_callback_payload == body
    assert application.status == ApplicationStatus.PAID.value
    assert db.committed


@pytest.mark.asyncio
async def test_payment_callback_is_idempotent_on_replay() -> None:
    payment = _make_payment(status=PaymentStatus.SUCCEEDED)
    payment.cdek_payment_id = 555
    payment.paid_at = _now()
    application = _make_application(status=ApplicationStatus.PAID)
    payment.application_id = application.id
    db = _FakeDB(payment=payment, application=application)

    body = {
        "payment": {"id": 555, "order_id": 999, "access_key": "ak1", "pay_amount": 1500000, "currency": "TST"},
        "signature": "x",
    }
    await handle_cdek_pay_payment_callback(db=db, body=body)

    # No re-write happened — committed flag stays False.
    assert db.committed is False


@pytest.mark.asyncio
async def test_payment_callback_does_not_downgrade_application_in_other_state() -> None:
    payment = _make_payment()
    application = _make_application(status=ApplicationStatus.ADMIN_REVIEW)
    payment.application_id = application.id
    db = _FakeDB(payment=payment, application=application)

    body = {
        "payment": {"id": 555, "order_id": 999, "access_key": "ak1", "pay_amount": 1500000, "currency": "TST"},
        "signature": "x",
    }
    await handle_cdek_pay_payment_callback(db=db, body=body)

    assert payment.status == PaymentStatus.SUCCEEDED.value
    # Application status unchanged because it's already past awaiting_payment.
    assert application.status == ApplicationStatus.ADMIN_REVIEW.value


@pytest.mark.asyncio
async def test_payment_callback_ignores_unknown_access_key() -> None:
    db = _FakeDB(payment=None)
    body = {"payment": {"id": 1, "access_key": "unknown"}, "signature": "x"}
    # Should silently return — no exception.
    await handle_cdek_pay_payment_callback(db=db, body=body)


@pytest.mark.asyncio
async def test_payment_callback_422_on_missing_fields() -> None:
    db = _FakeDB(payment=None)
    with pytest.raises(HTTPException) as exc:
        await handle_cdek_pay_payment_callback(db=db, body={"payment": {}})
    assert exc.value.status_code == 422


# ============================================================
# refund_success callback
# ============================================================


@pytest.mark.asyncio
async def test_refund_callback_marks_payment_refunded() -> None:
    payment = _make_payment(status=PaymentStatus.REFUND_REQUESTED)
    db = _FakeDB(payment=payment)
    body = {"payment": {"id": 555, "access_key": "ak1", "refund_amount": 1500000}, "signature": "x"}

    await handle_cdek_pay_refund_callback(db=db, body=body)

    assert payment.status == PaymentStatus.REFUNDED.value
    assert payment.refunded_at is not None


# ============================================================
# end-to-end signature → handler flow
# ============================================================


@pytest.mark.asyncio
async def test_handler_compatible_with_real_signature_scheme() -> None:
    """Симулирует то, что делает реальный webhook-router перед вызовом handler."""
    from app.services.cdek_pay import verify_callback_signature

    secret = "shop_secret"
    payment_payload = {
        "id": 777,
        "order_id": 1010,
        "access_key": "ak1",
        "pay_amount": 1500000,
        "currency": "TST",
    }
    signature = sign_payment_order(payment_payload, secret)
    assert verify_callback_signature(payment_payload, signature, secret) is True

    payment = _make_payment(access_key="ak1")
    application = _make_application()
    payment.application_id = application.id
    db = _FakeDB(payment=payment, application=application)

    await handle_cdek_pay_payment_callback(
        db=db,
        body={"payment": payment_payload, "signature": signature},
    )
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert application.status == ApplicationStatus.PAID.value
