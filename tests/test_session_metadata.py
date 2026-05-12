from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Response

from app.enums import UserRole
from app.models.user_session import UserSession
from app.services.auth_sessions import (
    LAST_SEEN_THROTTLE,
    SessionProfile,
    create_session,
    extract_request_metadata,
    should_update_last_seen,
)


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


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[UserSession] = []

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        for item in self.added:
            if isinstance(item, UserSession) and getattr(item, "id", None) is None:
                item.id = uuid4()


class _FakeRequest:
    def __init__(self, headers: dict[str, str], client_host: str | None = None) -> None:
        self.headers = headers
        self.client = SimpleNamespace(host=client_host) if client_host else None


def test_extract_request_metadata_prefers_x_forwarded_for() -> None:
    request = _FakeRequest(
        headers={"user-agent": "TestUA/1.0", "x-forwarded-for": "203.0.113.5, 10.0.0.1"},
        client_host="10.0.0.1",
    )
    ua, ip = extract_request_metadata(request)
    assert ua == "TestUA/1.0"
    assert ip == "203.0.113.5"


def test_extract_request_metadata_falls_back_to_client_host() -> None:
    request = _FakeRequest(headers={"user-agent": "UA"}, client_host="10.0.0.7")
    ua, ip = extract_request_metadata(request)
    assert ua == "UA"
    assert ip == "10.0.0.7"


def test_extract_request_metadata_handles_missing_client() -> None:
    request = _FakeRequest(headers={})
    ua, ip = extract_request_metadata(request)
    assert ua is None
    assert ip is None


@pytest.mark.asyncio
async def test_create_session_persists_device_metadata() -> None:
    db = _FakeDB()
    await create_session(
        db=db,
        user=_make_user(),
        response=Response(),
        profile=SessionProfile.MOBILE,
        user_agent="iPhone15,3 iOS/17.4",
        ip_address="203.0.113.5",
        device_name="Sergey's iPhone",
    )
    session = db.added[0]
    assert session.session_type == "mobile"
    assert session.device_name == "Sergey's iPhone"
    assert session.user_agent == "iPhone15,3 iOS/17.4"
    assert session.ip_address == "203.0.113.5"
    assert session.last_seen_at is not None


@pytest.mark.asyncio
async def test_create_session_trims_oversized_user_agent() -> None:
    db = _FakeDB()
    long_ua = "a" * 1000
    await create_session(
        db=db,
        user=_make_user(),
        response=Response(),
        user_agent=long_ua,
    )
    session = db.added[0]
    assert session.user_agent is not None
    assert len(session.user_agent) == 500


def test_should_update_last_seen_returns_true_when_never_seen() -> None:
    s = SimpleNamespace(last_seen_at=None)
    assert should_update_last_seen(s, datetime.now(timezone.utc)) is True


def test_should_update_last_seen_respects_throttle() -> None:
    now = datetime.now(timezone.utc)
    fresh = SimpleNamespace(last_seen_at=now - (LAST_SEEN_THROTTLE / 2))
    stale = SimpleNamespace(last_seen_at=now - LAST_SEEN_THROTTLE - timedelta(seconds=1))
    assert should_update_last_seen(fresh, now) is False
    assert should_update_last_seen(stale, now) is True
