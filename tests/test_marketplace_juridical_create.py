"""Public address_change c payer_type=juridical создаёт Payment(manual_invoice).

Initial registration всегда individual — поэтому отдельной ветки не имеет;
её покрывает test_marketplace_client_application.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import get_db
from app.enums import ApplicationStatus, PaymentPayerType, PaymentProvider, PaymentStatus, UserRole
from app.main import app
from app.models.application import Application
from app.models.client import Client
from app.models.payment import Payment
from app.models.user import User
from app.routers import marketplace as marketplace_router


def test_juridical_address_change_creates_manual_invoice_payment(monkeypatch) -> None:
    address_id = uuid4()
    provider_id = uuid4()
    now = datetime.now(timezone.utc)
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 1, помещение 5",
        price_6m=Decimal("15000.00"),
        price_11m=Decimal("25000.00"),
        correspondence_price=None,
        fns_number=46,
        fns_city="Москве",
        is_available=True,
        publication_status="published",
        created_at=now,
        updated_at=now,
    )
    provider = SimpleNamespace(id=provider_id, is_active=True)

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return None

        def scalar_one(self):
            return 0  # rate-limit count

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def get(self, model, object_id):
            if model.__name__ == "Address" and object_id == address_id:
                return address
            if model.__name__ == "Provider" and object_id == provider_id:
                return provider
            return None

        async def execute(self, _statement):
            return FakeScalarResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            for item in self.added:
                if getattr(item, "id", None) is None:
                    item.id = uuid4()
                if getattr(item, "created_at", None) is None:
                    item.created_at = now
                if getattr(item, "updated_at", None) is None:
                    item.updated_at = now

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.committed = False

        async def refresh(self, item):
            if getattr(item, "created_at", None) is None:
                item.created_at = now
            if getattr(item, "updated_at", None) is None:
                item.updated_at = now

    fake_db = FakeSession()

    async def override_db():
        yield fake_db

    # Bypass DaData: hand back a synthetic Client.
    async def fake_upsert(db, inn):
        client = Client(
            inn=inn,
            full_name="ООО Тест",
            short_name="ООО Тест",
        )
        client.id = uuid4()
        client.created_at = now
        client.updated_at = now
        return client

    monkeypatch.setattr(marketplace_router, "_upsert_client_from_dadata", fake_upsert)

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/marketplace/applications",
            json={
                "type": "address_change",
                "address_id": str(address_id),
                "client_inn": "7704217370",
                "contact_name": "Иван Юрик",
                "contact_email": "ur@example.com",
                "contact_phone": "+7 900 000-00-00",
                "password": "secret123",
                "term_months": 11,
                "notice_period": "1m",
                "has_correspondence_service": False,
                "payer_type": "juridical",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == UserRole.CLIENT.value
    assert body["application"]["status"] == ApplicationStatus.AWAITING_PAYMENT.value

    created_application = next(item for item in fake_db.added if isinstance(item, Application))
    created_payment = next(item for item in fake_db.added if isinstance(item, Payment))

    assert created_payment.application_id == created_application.id
    assert created_payment.provider == PaymentProvider.MANUAL_INVOICE.value
    assert created_payment.payer_type == PaymentPayerType.JURIDICAL.value
    assert created_payment.status == PaymentStatus.AWAITING_USER.value
    assert created_payment.amount_kopeks == 2_500_000  # 25 000 RUB * 100
    assert created_payment.currency == "RUR"


def test_juridical_individual_default_does_not_create_payment_row(monkeypatch) -> None:
    """При payer_type=individual (или его отсутствии) Payment не создаётся в create."""
    address_id = uuid4()
    provider_id = uuid4()
    now = datetime.now(timezone.utc)
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 1, помещение 5",
        price_6m=Decimal("15000.00"),
        price_11m=Decimal("25000.00"),
        correspondence_price=None,
        fns_number=46,
        fns_city="Москве",
        is_available=True,
        publication_status="published",
        created_at=now,
        updated_at=now,
    )
    provider = SimpleNamespace(id=provider_id, is_active=True)

    class FakeScalarResult:
        def scalar_one_or_none(self):
            return None

        def scalar_one(self):
            return 0

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def get(self, model, object_id):
            if model.__name__ == "Address" and object_id == address_id:
                return address
            if model.__name__ == "Provider" and object_id == provider_id:
                return provider
            return None

        async def execute(self, _statement):
            return FakeScalarResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            for item in self.added:
                if getattr(item, "id", None) is None:
                    item.id = uuid4()
                if getattr(item, "created_at", None) is None:
                    item.created_at = now
                if getattr(item, "updated_at", None) is None:
                    item.updated_at = now

        async def commit(self):
            self.committed = True

        async def rollback(self):
            self.committed = False

        async def refresh(self, item):
            if getattr(item, "created_at", None) is None:
                item.created_at = now
            if getattr(item, "updated_at", None) is None:
                item.updated_at = now

    fake_db = FakeSession()

    async def override_db():
        yield fake_db

    async def fake_upsert(db, inn):
        client = Client(inn=inn, full_name="ООО Тест", short_name="ООО Тест")
        client.id = uuid4()
        client.created_at = now
        client.updated_at = now
        return client

    monkeypatch.setattr(marketplace_router, "_upsert_client_from_dadata", fake_upsert)

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/marketplace/applications",
            json={
                "type": "address_change",
                "address_id": str(address_id),
                "client_inn": "7704217370",
                "contact_name": "Иван Физик",
                "contact_email": "fiz@example.com",
                "contact_phone": "+7 900 000-00-00",
                "password": "secret123",
                "term_months": 11,
                "notice_period": "1m",
                "has_correspondence_service": False,
                "payer_type": "individual",
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201, response.text
    payments_in_create = [item for item in fake_db.added if isinstance(item, Payment)]
    assert payments_in_create == []  # individual path: Payment is created later via /payments/initiate
