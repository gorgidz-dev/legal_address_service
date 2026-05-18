from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, PaymentPayerType, PaymentStatus, UserRole
from app.models.address import Address
from app.models.application import Application
from app.models.payment import Payment
from app.routers import payments as payments_router
from app.schemas.payment import PaymentInitiateRequest
from app.services.cdek_pay import CdekQrResponse


def _now():
    return datetime.now(timezone.utc)


def _make_address():
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
    a.publication_status = "published"
    a.is_available = True
    a.created_at = _now()
    a.updated_at = _now()
    return a


def _make_application(address, *, created_by, status=ApplicationStatus.AWAITING_PAYMENT, term_months=11):
    app = Application(
        type="initial_registration",
        status=status.value,
        provider_id=address.provider_id,
        address_id=address.id,
        company_name="Альфа",
        contact_name="Иван Иванов",
        contact_phone="+79001234567",
        contact_email="ivan@example.ru",
        term_months=term_months,
        has_correspondence_service=False,
        created_by=created_by,
    )
    app.id = uuid4()
    app.created_at = _now()
    app.updated_at = _now()
    return app


def _user(role: UserRole, user_id=None):
    return SimpleNamespace(
        id=user_id or uuid4(),
        email=f"{role.value}@example.ru",
        role=role.value,
        is_active=True,
    )


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *, address=None, application=None, existing_payment=None):
        self._address = address
        self._application = application
        self._existing_payment = existing_payment
        self.added: list = []
        self.committed = False

    async def get(self, model, key):
        if model is Application and self._application is not None and self._application.id == key:
            return self._application
        if model is Address and self._address is not None and self._address.id == key:
            return self._address
        return None

    async def execute(self, _stmt):
        # initiate() looks for existing active payment via select(Payment)
        return _ScalarResult(self._existing_payment)

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


class _FakeCdekService:
    """Минимальная заглушка cdek_pay сервиса."""

    def __init__(self, *, currency="TST"):
        self.currency = currency
        self.called_with = None

    async def generate_sbp_qr(self, **kwargs):
        self.called_with = kwargs
        return CdekQrResponse(
            qr_link="https://secure.cdekfin.ru/qr/abc",
            qr_image_base64="iVBORw0K...",
            order_id=123,
            access_key="ak-abc",
        )


@pytest.mark.asyncio
async def test_initiate_creates_payment_and_calls_cdek(monkeypatch) -> None:
    addr = _make_address()
    client = _user(UserRole.CLIENT)
    app = _make_application(addr, created_by=client.id)
    db = _FakeDB(address=addr, application=app)

    fake_service = _FakeCdekService()
    monkeypatch.setattr(payments_router, "get_cdek_pay_service", lambda: fake_service)

    result = await payments_router.initiate_payment(
        payload=PaymentInitiateRequest(
            application_id=app.id, payer_type=PaymentPayerType.INDIVIDUAL
        ),
        db=db,
        user=client,
    )

    assert result.status == PaymentStatus.AWAITING_USER.value
    assert result.amount_kopeks == 2_500_000  # 25000.00 RUB * 100
    assert result.currency == "TST"
    assert result.cdek_access_key == "ak-abc"
    assert result.qr_link.startswith("https://")
    assert db.committed
    assert fake_service.called_with["amount_kopeks"] == 2_500_000
    assert fake_service.called_with["user_phone"] == "79001234567"  # 11 digits


@pytest.mark.asyncio
async def test_initiate_returns_existing_active_payment(monkeypatch) -> None:
    addr = _make_address()
    client = _user(UserRole.CLIENT)
    app = _make_application(addr, created_by=client.id)
    existing = Payment(
        application_id=app.id,
        provider="cdek_pay",
        payer_type="individual",
        status=PaymentStatus.AWAITING_USER.value,
        amount_kopeks=2_500_000,
        currency="TST",
        pay_for="X",
        cdek_access_key="ak-old",
    )
    existing.id = uuid4()
    existing.created_at = _now()
    existing.updated_at = _now()
    db = _FakeDB(address=addr, application=app, existing_payment=existing)
    monkeypatch.setattr(payments_router, "get_cdek_pay_service", lambda: _FakeCdekService())

    result = await payments_router.initiate_payment(
        payload=PaymentInitiateRequest(
            application_id=app.id, payer_type=PaymentPayerType.INDIVIDUAL
        ),
        db=db,
        user=client,
    )
    assert result is existing
    assert db.committed is False  # no new commit


@pytest.mark.asyncio
async def test_initiate_403_for_foreign_client() -> None:
    addr = _make_address()
    owner_user = _user(UserRole.CLIENT)
    foreign = _user(UserRole.CLIENT)
    app = _make_application(addr, created_by=owner_user.id)
    db = _FakeDB(address=addr, application=app)

    with pytest.raises(HTTPException) as exc:
        await payments_router.initiate_payment(
            payload=PaymentInitiateRequest(
                application_id=app.id, payer_type=PaymentPayerType.INDIVIDUAL
            ),
            db=db,
            user=foreign,
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_initiate_409_when_application_not_awaiting_payment() -> None:
    addr = _make_address()
    client = _user(UserRole.CLIENT)
    app = _make_application(addr, created_by=client.id, status=ApplicationStatus.PAID)
    db = _FakeDB(address=addr, application=app)

    with pytest.raises(HTTPException) as exc:
        await payments_router.initiate_payment(
            payload=PaymentInitiateRequest(
                application_id=app.id, payer_type=PaymentPayerType.INDIVIDUAL
            ),
            db=db,
            user=client,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_initiate_includes_correspondence_price_when_enabled(monkeypatch) -> None:
    addr = _make_address()
    addr.correspondence_price = Decimal("3000.00")
    client = _user(UserRole.CLIENT)
    app = _make_application(addr, created_by=client.id)
    app.has_correspondence_service = True
    db = _FakeDB(address=addr, application=app)
    fake_service = _FakeCdekService()
    monkeypatch.setattr(payments_router, "get_cdek_pay_service", lambda: fake_service)

    result = await payments_router.initiate_payment(
        payload=PaymentInitiateRequest(
            application_id=app.id, payer_type=PaymentPayerType.INDIVIDUAL
        ),
        db=db,
        user=client,
    )
    # Почта помесячно × срок: 25000 + 3000×11 = 58000.00
    assert result.amount_kopeks == 5_800_000


def test_only_ru_phone_digits_helper() -> None:
    helper = payments_router._only_ru_phone_digits
    assert helper("+79001234567") == "79001234567"
    assert helper("89001234567") == "89001234567"
    assert helper("9001234567") == "79001234567"
    assert helper(None) is None
    assert helper("") is None
    assert helper("123") is None  # too short
