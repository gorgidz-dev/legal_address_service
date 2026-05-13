"""Юр.лица: ручное подтверждение оплаты (mark-paid / reject-payment).

Не тестирует CDEK Pay flow — он живёт в test_cdek_pay_*.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, PaymentPayerType, PaymentProvider, PaymentStatus, UserRole
from app.models.application import Application
from app.models.payment import Payment
from app.routers.payments import (
    mark_payment_paid,
    reject_manual_payment,
)
from app.schemas.payment import PaymentManualConfirmRequest, PaymentRejectRequest


def _now():
    return datetime.now(timezone.utc)


def _make_payment(provider: PaymentProvider, status: PaymentStatus, *, application_id=None):
    p = Payment(
        application_id=application_id or uuid4(),
        provider=provider.value,
        payer_type=PaymentPayerType.JURIDICAL.value,
        status=status.value,
        amount_kopeks=2_500_000,
        currency="RUR",
        pay_for="Юр. адрес: Тест",
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


def _admin():
    return SimpleNamespace(id=uuid4(), email="a@x", role=UserRole.ADMIN.value, is_active=True)


class _FakeDB:
    def __init__(self, *, payment=None, application=None):
        self._payment = payment
        self._application = application
        self.added = []
        self.committed = False

    async def get(self, model, key):
        if model is Payment and self._payment is not None and self._payment.id == key:
            return self._payment
        if model is Application and self._application is not None and self._application.id == key:
            return self._application
        return None

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
# mark-paid
# ============================================================


@pytest.mark.asyncio
async def test_mark_paid_succeeded_path_transitions_application() -> None:
    app = _make_application()
    payment = _make_payment(PaymentProvider.MANUAL_INVOICE, PaymentStatus.AWAITING_USER, application_id=app.id)
    db = _FakeDB(payment=payment, application=app)

    result = await mark_payment_paid(
        payment_id=payment.id,
        payload=PaymentManualConfirmRequest(comment="платёж пришёл из Сбера"),
        db=db,
        admin=_admin(),
    )

    assert result.status == PaymentStatus.SUCCEEDED.value
    assert result.paid_at is not None
    assert app.status == ApplicationStatus.PAID.value
    assert db.committed


@pytest.mark.asyncio
async def test_mark_paid_rejects_cdek_pay_provider() -> None:
    payment = _make_payment(PaymentProvider.CDEK_PAY, PaymentStatus.AWAITING_USER)
    db = _FakeDB(payment=payment)

    with pytest.raises(HTTPException) as exc:
        await mark_payment_paid(
            payment_id=payment.id,
            payload=PaymentManualConfirmRequest(),
            db=db,
            admin=_admin(),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_mark_paid_rejects_already_succeeded() -> None:
    payment = _make_payment(PaymentProvider.MANUAL_INVOICE, PaymentStatus.SUCCEEDED)
    db = _FakeDB(payment=payment)

    with pytest.raises(HTTPException) as exc:
        await mark_payment_paid(
            payment_id=payment.id,
            payload=PaymentManualConfirmRequest(),
            db=db,
            admin=_admin(),
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_mark_paid_does_not_downgrade_application_outside_awaiting_payment() -> None:
    app = _make_application(status=ApplicationStatus.ADMIN_REVIEW)
    payment = _make_payment(PaymentProvider.MANUAL_INVOICE, PaymentStatus.AWAITING_USER, application_id=app.id)
    db = _FakeDB(payment=payment, application=app)

    await mark_payment_paid(
        payment_id=payment.id,
        payload=PaymentManualConfirmRequest(),
        db=db,
        admin=_admin(),
    )

    assert payment.status == PaymentStatus.SUCCEEDED.value
    # Application stays where it was (e.g. admin already moved it).
    assert app.status == ApplicationStatus.ADMIN_REVIEW.value


# ============================================================
# reject-payment
# ============================================================


@pytest.mark.asyncio
async def test_reject_marks_failed_with_reason() -> None:
    app = _make_application()
    payment = _make_payment(PaymentProvider.MANUAL_INVOICE, PaymentStatus.AWAITING_USER, application_id=app.id)
    db = _FakeDB(payment=payment, application=app)

    result = await reject_manual_payment(
        payment_id=payment.id,
        payload=PaymentRejectRequest(reason="перевод не поступил за 5 рабочих дней"),
        db=db,
        admin=_admin(),
    )

    assert result.status == PaymentStatus.FAILED.value
    assert "перевод не поступил" in (result.last_callback_payload or {}).get("reason", "")
    # Application stays in awaiting_payment so user can retry.
    assert app.status == ApplicationStatus.AWAITING_PAYMENT.value


@pytest.mark.asyncio
async def test_reject_rejects_cdek_pay_provider() -> None:
    payment = _make_payment(PaymentProvider.CDEK_PAY, PaymentStatus.AWAITING_USER)
    db = _FakeDB(payment=payment)

    with pytest.raises(HTTPException) as exc:
        await reject_manual_payment(
            payment_id=payment.id,
            payload=PaymentRejectRequest(reason="no"),
            db=db,
            admin=_admin(),
        )
    assert exc.value.status_code == 409


# ============================================================
# Public create with payer_type=juridical creates the placeholder Payment
# (covered at integration level via test_marketplace_client_application_juridical)
# ============================================================
