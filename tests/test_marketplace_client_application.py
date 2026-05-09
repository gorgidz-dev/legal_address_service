from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import get_db
from app.enums import ApplicationStatus, UserRole
from app.main import _is_public_path, app
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.user import User
from app.schemas.marketplace import PublicClientApplicationCreateInitial


def test_marketplace_application_create_is_public_post_only() -> None:
    assert _is_public_path("/marketplace/applications", "POST")
    assert not _is_public_path("/marketplace/applications", "GET")


def test_public_client_application_schema_normalizes_email() -> None:
    payload = PublicClientApplicationCreateInitial(
        address_id=uuid4(),
        planned_client_name="Альфа",
        contact_name="Иван Клиентов",
        contact_email="CLIENT@Example.COM",
        password="secret123",
        term_months=11,
    )

    assert payload.contact_email == "CLIENT@example.com"


def test_public_initial_application_creates_client_user_application_and_session() -> None:
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

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/marketplace/applications",
            json={
                "type": "initial_registration",
                "address_id": str(address_id),
                "planned_client_name": "Альфа",
                "contact_name": "Иван Клиентов",
                "contact_email": "client@example.com",
                "contact_phone": "+7 900 000-00-00",
                "password": "secret123",
                "term_months": 11,
                "has_correspondence_service": False,
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == UserRole.CLIENT.value
    assert body["application"]["status"] == ApplicationStatus.ADMIN_REVIEW.value
    assert response.cookies.get("legal_address_session")

    created_user = next(item for item in fake_db.added if isinstance(item, User))
    created_application = next(item for item in fake_db.added if isinstance(item, Application))
    created_event = next(item for item in fake_db.added if isinstance(item, ApplicationEvent))
    assert created_user.email == "client@example.com"
    assert created_application.created_by == created_user.id
    assert created_application.address_id == address_id
    assert created_application.provider_id == provider_id
    assert created_application.company_name == "Альфа"
    assert created_event.application_id == created_application.id
    assert created_event.audience == "client"
    assert created_event.payload["status"] == ApplicationStatus.ADMIN_REVIEW.value
