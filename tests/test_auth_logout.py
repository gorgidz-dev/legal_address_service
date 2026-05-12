from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import Response

from app.enums import UserRole
from app.models.user_session import UserSession
from app.routers.auth import list_my_sessions, logout, logout_all_others


def _now():
    return datetime.now(timezone.utc)


def _make_user():
    n = _now()
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        full_name="Тест",
        role=UserRole.CLIENT.value,
        is_active=True,
        created_at=n,
        updated_at=n,
    )


def _make_session(user_id: UUID, *, revoked: bool = False, expired: bool = False) -> UserSession:
    n = _now()
    s = UserSession(
        user_id=user_id,
        token_hash=f"hash-{uuid4()}",
        expires_at=(n - timedelta(hours=1)) if expired else (n + timedelta(hours=24)),
        created_at=n,
    )
    s.id = uuid4()
    if revoked:
        s.revoked_at = n
    return s


class _FakeRequest:
    def __init__(self, session_id):
        self.state = SimpleNamespace(session_id=session_id)


class _FakeDB:
    def __init__(self, sessions: list[UserSession]):
        self._sessions = sessions
        self.committed = False

    async def get(self, model, key):
        for s in self._sessions:
            if s.id == key:
                return s
        return None

    async def execute(self, _stmt):
        # naive: return all sessions matching active-status (caller filters)
        # in real code SQLAlchemy parses the where clause, here we just return all
        # and the test expects logic in the endpoint to set revoked_at correctly
        # since we can't easily evaluate WHERE on Python objects, return the
        # full list and rely on endpoint pre-filtering not being used here.
        # For logout-all and list_sessions tests, we'll provide pre-filtered data.
        results = self._sessions

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_innermost):
                        return list(results)

                return _S()

            def first(self_inner):
                return results[0] if results else None

        return _R()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_logout_revokes_only_current_session() -> None:
    user = _make_user()
    current = _make_session(user.id)
    other = _make_session(user.id)
    db = _FakeDB([current, other])

    response = Response()
    request = _FakeRequest(current.id)
    await logout(request=request, response=response, db=db, user=user)

    assert current.revoked_at is not None
    assert other.revoked_at is None
    assert db.committed
    # logout deletes cookies
    raw = response.headers.getlist("set-cookie")
    assert any("legal_address_session" in c for c in raw)
    assert any("legal_address_refresh" in c for c in raw)


@pytest.mark.asyncio
async def test_logout_skips_when_no_session_id_on_state() -> None:
    user = _make_user()
    current = _make_session(user.id)
    db = _FakeDB([current])
    response = Response()
    request = _FakeRequest(None)

    await logout(request=request, response=response, db=db, user=user)

    assert current.revoked_at is None
    assert not db.committed


@pytest.mark.asyncio
async def test_logout_all_others_keeps_current_active() -> None:
    user = _make_user()
    current = _make_session(user.id)
    other_a = _make_session(user.id)
    other_b = _make_session(user.id)
    # Only return the "other" sessions, since real SQL would exclude current
    db = _FakeDB([other_a, other_b])

    request = _FakeRequest(current.id)
    await logout_all_others(request=request, db=db, user=user)

    assert other_a.revoked_at is not None
    assert other_b.revoked_at is not None
    assert current.revoked_at is None
    assert db.committed


@pytest.mark.asyncio
async def test_list_my_sessions_marks_current() -> None:
    user = _make_user()
    s1 = _make_session(user.id)
    s2 = _make_session(user.id)
    db = _FakeDB([s1, s2])
    request = _FakeRequest(s1.id)

    result = await list_my_sessions(request=request, db=db, user=user)

    assert len(result) == 2
    current_ids = [r.id for r in result if r.is_current]
    assert current_ids == [s1.id]
