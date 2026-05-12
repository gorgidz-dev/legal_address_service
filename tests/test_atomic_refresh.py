from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.auth_sessions import atomic_consume_refresh


def _now():
    return datetime.now(timezone.utc)


class _FakeDB:
    """Fake DB that evaluates the UPDATE-RETURNING atomically against an in-memory store."""

    def __init__(self, sessions: list[UserSession]):
        self.sessions = sessions

    async def execute(self, stmt):
        # Extract the WHERE clause values
        clauses = stmt.whereclause.clauses if hasattr(stmt.whereclause, "clauses") else [stmt.whereclause]
        target_hash = None
        cutoff = None
        for c in clauses:
            text = str(c)
            if "refresh_token_hash = " in text:
                target_hash = c.right.value
            elif "refresh_expires_at > " in text:
                cutoff = c.right.value
        # Extract values being set (revoked_at, last_refreshed_at) — _values is keyed by Column
        new_revoked = None
        new_refreshed = None
        for col, bind in stmt._values.items():
            if col.name == "revoked_at":
                new_revoked = bind.value
            elif col.name == "last_refreshed_at":
                new_refreshed = bind.value

        # Atomic operation: find the FIRST matching active session, revoke it, return it.
        # Subsequent calls with same token will see revoked_at set and find nothing.
        for s in self.sessions:
            if (
                s.refresh_token_hash == target_hash
                and s.revoked_at is None
                and (cutoff is None or s.refresh_expires_at > cutoff)
            ):
                s.revoked_at = new_revoked
                s.last_refreshed_at = new_refreshed

                class _R:
                    def first(self_inner):
                        from types import SimpleNamespace

                        return SimpleNamespace(user_id=s.user_id, device_name=s.device_name)

                return _R()

        class _Empty:
            def first(self_inner):
                return None

        return _Empty()


def _make_session(*, revoked: bool = False, expired: bool = False) -> tuple[UserSession, str]:
    raw_token = f"raw-{uuid4()}"
    n = _now()
    s = UserSession(
        user_id=uuid4(),
        token_hash="access-hash",
        expires_at=n + timedelta(hours=24),
        refresh_token_hash=hash_token(raw_token),
        refresh_expires_at=(n - timedelta(hours=1)) if expired else (n + timedelta(days=30)),
        created_at=n,
        device_name="iPhone",
    )
    s.id = uuid4()
    if revoked:
        s.revoked_at = n
    return s, raw_token


@pytest.mark.asyncio
async def test_atomic_consume_refresh_revokes_and_returns_info() -> None:
    session, raw = _make_session()
    db = _FakeDB([session])

    info = await atomic_consume_refresh(db, raw)

    assert info is not None
    assert info.user_id == session.user_id
    assert info.device_name == "iPhone"
    assert session.revoked_at is not None


@pytest.mark.asyncio
async def test_atomic_consume_refresh_second_use_fails() -> None:
    """Concurrent/replayed refresh — only the first attempt revokes; second returns None."""
    session, raw = _make_session()
    db = _FakeDB([session])

    first = await atomic_consume_refresh(db, raw)
    second = await atomic_consume_refresh(db, raw)

    assert first is not None
    assert second is None  # already revoked


@pytest.mark.asyncio
async def test_atomic_consume_refresh_rejects_expired() -> None:
    session, raw = _make_session(expired=True)
    db = _FakeDB([session])

    info = await atomic_consume_refresh(db, raw)
    assert info is None
    assert session.revoked_at is None  # not revoked because didn't match


@pytest.mark.asyncio
async def test_atomic_consume_refresh_rejects_already_revoked() -> None:
    session, raw = _make_session(revoked=True)
    db = _FakeDB([session])

    info = await atomic_consume_refresh(db, raw)
    assert info is None


@pytest.mark.asyncio
async def test_atomic_consume_refresh_unknown_token() -> None:
    session, _raw = _make_session()
    db = _FakeDB([session])

    info = await atomic_consume_refresh(db, "definitely-not-the-token")
    assert info is None
    assert session.revoked_at is None
