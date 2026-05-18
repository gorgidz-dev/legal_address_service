"""Документы платежа: роли доступа и подтверждение поступления средств.

Роут-функции вызываются напрямую — HTTP-слой за auth-middleware с реальной БД.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import (
    ApplicationStatus,
    PaymentProvider,
    PaymentStatus,
    UserRole,
)
from app.models.address import Address
from app.models.application import Application
from app.models.payment import Payment
from app.routers.payments import (
    _payment_role,
    confirm_payment_receipt,
    list_payment_attachments,
)
from app.schemas.payment import PaymentReceiptConfirm


# ----------------------------- fixtures -----------------------------

def _address(provider_id=None):
    return SimpleNamespace(id=uuid4(), provider_id=provider_id or uuid4())


def _application(*, created_by, address_id, status=ApplicationStatus.AWAITING_PAYMENT.value):
    return SimpleNamespace(
        id=uuid4(), created_by=created_by, address_id=address_id, status=status
    )


def _payment(*, application_id, provider=PaymentProvider.MANUAL_INVOICE.value,
             status=PaymentStatus.AWAITING_USER.value):
    return SimpleNamespace(
        id=uuid4(),
        application_id=application_id,
        provider=provider,
        status=status,
        paid_at=None,
    )


class _FakeSession:
    def __init__(self, get_map=None):
        self._get_map = get_map or {}
        self.committed = False
        self.added = []

    async def get(self, model, pk):
        return self._get_map.get((model, pk))

    async def execute(self, _stmt):
        class _R:
            def all(self_inner):
                return []

            def scalars(self_inner):
                return self_inner

            def first(self_inner):
                return None

        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        pass


# ----------------------------- _payment_role -----------------------------

def test_payment_role_matrix():
    prov = uuid4()
    addr = _address(provider_id=prov)
    client_id = uuid4()
    app = _application(created_by=client_id, address_id=addr.id)

    client = SimpleNamespace(id=client_id, role=UserRole.CLIENT.value, provider_id=None)
    assert _payment_role(client, app, addr) == "client"

    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=prov)
    assert _payment_role(owner, app, addr) == "owner"

    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value, provider_id=None)
    assert _payment_role(admin, app, addr) == "staff"

    # чужой клиент
    other = SimpleNamespace(id=uuid4(), role=UserRole.CLIENT.value, provider_id=None)
    assert _payment_role(other, app, addr) is None

    # owner другого провайдера
    foreign_owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=uuid4())
    assert _payment_role(foreign_owner, app, addr) is None


# ----------------------------- confirm_payment_receipt -----------------------------

@pytest.mark.asyncio
async def test_confirm_receipt_owner_succeeds():
    prov = uuid4()
    addr = _address(provider_id=prov)
    app = _application(created_by=uuid4(), address_id=addr.id)
    pay = _payment(application_id=app.id)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=prov)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    result = await confirm_payment_receipt(
        pay.id, PaymentReceiptConfirm(comment="платёж от 14.05"), db=db, user=owner
    )
    assert result.status == PaymentStatus.SUCCEEDED.value
    assert app.status == ApplicationStatus.PAID.value
    assert pay.paid_at is not None
    assert db.committed is True


@pytest.mark.asyncio
async def test_confirm_receipt_non_owner_forbidden():
    prov = uuid4()
    addr = _address(provider_id=prov)
    app = _application(created_by=uuid4(), address_id=addr.id)
    pay = _payment(application_id=app.id)
    # клиент пытается подтвердить — нельзя
    client = SimpleNamespace(id=app.created_by, role=UserRole.CLIENT.value, provider_id=None)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    with pytest.raises(HTTPException) as exc:
        await confirm_payment_receipt(
            pay.id, PaymentReceiptConfirm(), db=db, user=client
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_confirm_receipt_rejects_cdek_pay():
    prov = uuid4()
    addr = _address(provider_id=prov)
    app = _application(created_by=uuid4(), address_id=addr.id)
    pay = _payment(application_id=app.id, provider=PaymentProvider.CDEK_PAY.value)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=prov)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    with pytest.raises(HTTPException) as exc:
        await confirm_payment_receipt(pay.id, PaymentReceiptConfirm(), db=db, user=owner)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_confirm_receipt_rejects_already_paid():
    prov = uuid4()
    addr = _address(provider_id=prov)
    app = _application(created_by=uuid4(), address_id=addr.id)
    pay = _payment(application_id=app.id, status=PaymentStatus.SUCCEEDED.value)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=prov)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    with pytest.raises(HTTPException) as exc:
        await confirm_payment_receipt(pay.id, PaymentReceiptConfirm(), db=db, user=owner)
    assert exc.value.status_code == 409


# ----------------------------- list access gate -----------------------------

@pytest.mark.asyncio
async def test_list_attachments_foreign_user_forbidden():
    prov = uuid4()
    addr = _address(provider_id=prov)
    app = _application(created_by=uuid4(), address_id=addr.id)
    pay = _payment(application_id=app.id)
    stranger = SimpleNamespace(id=uuid4(), role=UserRole.CLIENT.value, provider_id=None)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    with pytest.raises(HTTPException) as exc:
        await list_payment_attachments(pay.id, db=db, user=stranger)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_attachments_client_ok():
    prov = uuid4()
    addr = _address(provider_id=prov)
    client_id = uuid4()
    app = _application(created_by=client_id, address_id=addr.id)
    pay = _payment(application_id=app.id)
    client = SimpleNamespace(id=client_id, role=UserRole.CLIENT.value, provider_id=None)
    db = _FakeSession(get_map={
        (Payment, pay.id): pay,
        (Application, app.id): app,
        (Address, addr.id): addr,
    })
    result = await list_payment_attachments(pay.id, db=db, user=client)
    assert result == []
