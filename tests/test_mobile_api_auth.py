from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.database import get_db
from app.enums import UserRole
from app.main import _is_public_path, _session_token_from_request, app
from app.models.user_session import UserSession
from app.services.auth_security import hash_password


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/auth/me",
            "headers": headers,
        }
    )


def test_mobile_auth_login_is_public() -> None:
    assert _is_public_path("/mobile/auth/login", "POST")


def test_session_token_from_request_prefers_cookie_then_bearer_header() -> None:
    cookie_request = _request_with_headers(
        [
            (b"cookie", b"legal_address_session=web-token"),
            (b"authorization", b"Bearer mobile-token"),
        ]
    )
    bearer_request = _request_with_headers([(b"authorization", b"Bearer mobile-token")])
    malformed_request = _request_with_headers([(b"authorization", b"Basic mobile-token")])

    assert _session_token_from_request(cookie_request) == "web-token"
    assert _session_token_from_request(bearer_request) == "mobile-token"
    assert _session_token_from_request(malformed_request) is None


def test_mobile_login_returns_bearer_session_without_setting_cookie() -> None:
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(
        id=uuid4(),
        email="client@example.com",
        full_name="Мария Клиентова",
        password_hash=hash_password("secret123"),
        role=UserRole.CLIENT.value,
        is_active=True,
        provider_id=None,
        created_at=now,
        updated_at=now,
    )

    class FakeScalarResult:
        def __init__(self, mode="user"):
            self._mode = mode

        def scalar_one_or_none(self):
            return user

        def scalar_one(self):
            return 0  # rate-limit count: no prior attempts

    class FakeSession:
        def __init__(self):
            self.added = []
            self.committed = False

        async def execute(self, _statement):
            return FakeScalarResult()

        def add(self, item):
            self.added.append(item)

        async def flush(self):
            for item in self.added:
                if getattr(item, "id", None) is None:
                    item.id = uuid4()
                if isinstance(item, UserSession) and getattr(item, "expires_at", None) is None:
                    item.expires_at = now + timedelta(hours=12)

        async def commit(self):
            self.committed = True

        async def refresh(self, _item):
            return None

    fake_db = FakeSession()

    async def override_db():
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/mobile/auth/login",
            json={"email": "CLIENT@example.com", "password": "secret123"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "client@example.com"
    assert body["session"]["token_type"] == "bearer"
    assert body["session"]["access_token"]
    assert body["session"]["expires_at"]
    assert response.cookies.get("legal_address_session") is None
    assert fake_db.committed
    assert any(isinstance(item, UserSession) for item in fake_db.added)
