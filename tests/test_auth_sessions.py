from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.config import Settings, settings as global_settings
from app.enums import UserRole
from app.models.user_session import UserSession
from app.services.auth_sessions import SessionProfile, create_session, set_session_cookie


def _make_user():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        full_name="Тест",
        role=UserRole.CLIENT.value,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, UserSession) and getattr(item, "id", None) is None:
                item.id = uuid4()


def test_settings_reject_samesite_none_without_secure() -> None:
    with pytest.raises(ValidationError):
        Settings(
            session_cookie_secure=False,
            session_cookie_samesite="none",
        )


def test_settings_accept_samesite_none_with_secure() -> None:
    cfg = Settings(
        session_cookie_secure=True,
        session_cookie_samesite="none",
    )
    assert cfg.session_cookie_samesite == "none"
    assert cfg.session_cookie_secure is True


def test_settings_default_ttls() -> None:
    cfg = Settings()
    assert cfg.web_session_ttl_hours == 24
    assert cfg.mobile_session_ttl_hours == 24 * 7


def test_set_session_cookie_uses_settings_attributes(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "session_cookie_secure", True)
    monkeypatch.setattr(global_settings, "session_cookie_samesite", "strict")
    monkeypatch.setattr(global_settings, "session_cookie_domain", ".example.com")

    response = Response()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    set_session_cookie(response, "tok", expires_at)

    raw = response.headers.get("set-cookie", "")
    assert "Secure" in raw
    assert "SameSite=strict" in raw.lower() or "samesite=strict" in raw.lower()
    assert "Domain=.example.com" in raw or "domain=.example.com" in raw.lower()
    assert "HttpOnly" in raw or "httponly" in raw.lower()


@pytest.mark.asyncio
async def test_create_session_web_uses_web_ttl_and_sets_cookie(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "web_session_ttl_hours", 24)

    user = _make_user()
    db = _FakeSession()
    response = Response()

    creds = await create_session(db=db, user=user, response=response, profile=SessionProfile.WEB)

    delta = creds.expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=23, minutes=55) <= delta <= timedelta(hours=24, minutes=5)
    assert response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_create_session_mobile_uses_mobile_ttl_and_no_cookie(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "mobile_session_ttl_hours", 24 * 7)

    user = _make_user()
    db = _FakeSession()
    response = Response()

    creds = await create_session(db=db, user=user, response=response, profile=SessionProfile.MOBILE)

    delta = creds.expires_at - datetime.now(timezone.utc)
    assert timedelta(hours=24 * 7 - 1) <= delta <= timedelta(hours=24 * 7 + 1)
    assert response.headers.get("set-cookie", "") == ""


@pytest.mark.asyncio
async def test_create_session_web_default_profile(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "web_session_ttl_hours", 24)

    user = _make_user()
    db = _FakeSession()
    response = Response()

    creds = await create_session(db=db, user=user, response=response)

    delta = creds.expires_at - datetime.now(timezone.utc)
    assert delta <= timedelta(hours=25)
    assert response.headers.get("set-cookie", "")
