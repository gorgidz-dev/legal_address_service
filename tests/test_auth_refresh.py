from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response

from app.config import settings as global_settings
from app.enums import UserRole
from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.auth_sessions import SessionProfile, create_session, rotate_session


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


@pytest.mark.asyncio
async def test_create_session_returns_refresh_credentials(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "web_session_ttl_hours", 24)
    monkeypatch.setattr(global_settings, "web_refresh_ttl_hours", 24 * 30)

    user = _make_user()
    db = _FakeSession()
    response = Response()

    creds = await create_session(db=db, user=user, response=response, profile=SessionProfile.WEB)

    assert creds.token and creds.refresh_token
    assert creds.token != creds.refresh_token
    assert creds.expires_at < creds.refresh_expires_at

    assert len(db.added) == 1
    session: UserSession = db.added[0]
    assert session.token_hash == hash_token(creds.token)
    assert session.refresh_token_hash == hash_token(creds.refresh_token)


@pytest.mark.asyncio
async def test_create_session_web_sets_both_cookies(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "web_session_ttl_hours", 24)
    monkeypatch.setattr(global_settings, "web_refresh_ttl_hours", 24 * 30)

    db = _FakeSession()
    response = Response()
    await create_session(db=db, user=_make_user(), response=response, profile=SessionProfile.WEB)

    cookies = response.headers.getlist("set-cookie")
    assert any(global_settings.session_cookie_name in c for c in cookies)
    assert any(global_settings.refresh_cookie_name in c for c in cookies)
    assert any(f"Path={global_settings.refresh_cookie_path}" in c for c in cookies)


@pytest.mark.asyncio
async def test_mobile_refresh_ttl_longer(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "mobile_session_ttl_hours", 24 * 7)
    monkeypatch.setattr(global_settings, "mobile_refresh_ttl_hours", 24 * 90)

    db = _FakeSession()
    creds = await create_session(db=db, user=_make_user(), profile=SessionProfile.MOBILE)

    access_window = creds.expires_at - datetime.now(timezone.utc)
    refresh_window = creds.refresh_expires_at - datetime.now(timezone.utc)
    assert access_window < refresh_window
    assert refresh_window > timedelta(days=89)


@pytest.mark.asyncio
async def test_rotate_session_revokes_old_and_issues_new(monkeypatch) -> None:
    monkeypatch.setattr(global_settings, "web_session_ttl_hours", 24)
    monkeypatch.setattr(global_settings, "web_refresh_ttl_hours", 24 * 30)

    user = _make_user()
    db = _FakeSession()
    response = Response()
    first = await create_session(db=db, user=user, response=response, profile=SessionProfile.WEB)
    old_session: UserSession = db.added[0]

    second = await rotate_session(
        db=db,
        old_session=old_session,
        user=user,
        response=Response(),
        profile=SessionProfile.WEB,
    )

    assert old_session.revoked_at is not None
    assert old_session.last_refreshed_at is not None
    assert second.token != first.token
    assert second.refresh_token != first.refresh_token
    assert len(db.added) == 2
