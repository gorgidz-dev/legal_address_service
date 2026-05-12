from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import _is_public_path, app
from app.routers.marketplace import public_address_from_row


def test_marketplace_public_paths_do_not_require_auth() -> None:
    assert _is_public_path("/api/v1/marketplace/addresses", "GET")
    assert _is_public_path("/api/v1/marketplace/provider-requests", "POST")
    assert not _is_public_path("/api/v1/marketplace/provider-requests", "GET")


def test_public_address_from_row_uses_selected_term_price() -> None:
    address_id = uuid4()
    provider_id = uuid4()
    now = datetime.now(timezone.utc)
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 7, офис 41",
        room_number="офис 41",
        price_6m=Decimal("18000.00"),
        price_11m=Decimal("30000.00"),
        correspondence_price=Decimal("3500.00"),
        fns_number=46,
        fns_city="Москве",
        is_available=True,
        publication_status="published",
        created_at=now,
        updated_at=now,
    )
    provider = SimpleNamespace(short_name="Московский адресный фонд")

    payload = public_address_from_row(address=address, provider=provider, term_months=11)

    assert payload.id == address_id
    assert payload.provider_name == "Московский адресный фонд"
    assert payload.selected_price == Decimal("30000.00")


def test_public_addresses_endpoint_accepts_term_months_query() -> None:
    now = datetime.now(timezone.utc)
    address = SimpleNamespace(
        id=uuid4(),
        provider_id=uuid4(),
        full_address="г. Москва, ул. Никольская, д. 10, помещение 2",
        room_number="помещение 2",
        price_6m=Decimal("21000.00"),
        price_11m=Decimal("36000.00"),
        correspondence_price=None,
        fns_number=46,
        fns_city="Москве",
        is_available=True,
        publication_status="published",
        created_at=now,
        updated_at=now,
    )
    provider = SimpleNamespace(short_name="Адресный актив")

    class FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    class FakeResult:
        def __init__(self, rows=None, scalars=None):
            self._rows = rows or []
            self._scalars = scalars or []

        def all(self):
            return self._rows

        def scalars(self):
            return FakeScalars(self._scalars)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(rows=[(address, provider)])
            # Второй вызов — батч-загрузка одобренных фото; в тесте их нет.
            return FakeResult(scalars=[])

    async def override_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).get("/api/v1/marketplace/addresses?term_months=11")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["selected_price"] == "36000.00"
    assert body[0]["photos"] == []
    assert body[0]["main_photo_url"] is None
