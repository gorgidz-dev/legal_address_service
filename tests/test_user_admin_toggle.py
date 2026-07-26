"""Включение/отключение учётных записей админом (`PATCH /auth/users/{id}`)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import UserRole
from app.main import _is_public_path
from app.routers.auth import set_user_active
from app.schemas.auth import UserActiveUpdate


def _user(*, role: str = UserRole.MANAGER.value, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        full_name="Пользователь",
        role=role,
        is_active=is_active,
        provider_id=None,
        created_at=datetime.now(timezone.utc),
    )


class FakeScalars:
    def __init__(self, items: list):
        self._items = items

    def all(self) -> list:
        return self._items


class FakeResult:
    def __init__(self, items: list):
        self._items = items

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._items)


class FakeSession:
    """Минимальная замена AsyncSession: отдаёт заданного пользователя и сессии."""

    def __init__(self, user, sessions: list | None = None):
        self._user = user
        self._sessions = sessions or []
        self.committed = False

    async def get(self, _model, _pk):
        return self._user

    async def execute(self, _statement):
        return FakeResult(self._sessions)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _obj) -> None:
        return None


def test_user_admin_endpoints_are_not_public() -> None:
    assert not _is_public_path("/api/v1/auth/users", "GET")
    assert not _is_public_path(f"/api/v1/auth/users/{uuid4()}", "PATCH")


@pytest.mark.asyncio
async def test_admin_cannot_disable_himself() -> None:
    admin = _user(role=UserRole.ADMIN.value)
    db = FakeSession(admin)

    with pytest.raises(HTTPException) as exc:
        await set_user_active(admin.id, UserActiveUpdate(is_active=False), db=db, admin=admin)

    assert exc.value.status_code == 400
    assert admin.is_active is True
    assert db.committed is False


@pytest.mark.asyncio
async def test_disabling_user_revokes_live_sessions() -> None:
    admin = _user(role=UserRole.ADMIN.value)
    target = _user(role=UserRole.ADMIN.value)
    live = SimpleNamespace(revoked_at=None)
    db = FakeSession(target, sessions=[live])

    result = await set_user_active(
        target.id, UserActiveUpdate(is_active=False), db=db, admin=admin
    )

    assert result.is_active is False
    # Иначе refresh-токен выдал бы отключённому пользователю новый доступ.
    assert live.revoked_at is not None
    assert db.committed is True


@pytest.mark.asyncio
async def test_enabling_user_does_not_touch_sessions() -> None:
    admin = _user(role=UserRole.ADMIN.value)
    target = _user(is_active=False)
    stale = SimpleNamespace(revoked_at=None)
    db = FakeSession(target, sessions=[stale])

    result = await set_user_active(
        target.id, UserActiveUpdate(is_active=True), db=db, admin=admin
    )

    assert result.is_active is True
    assert stale.revoked_at is None


@pytest.mark.asyncio
async def test_repeated_state_is_a_noop() -> None:
    admin = _user(role=UserRole.ADMIN.value)
    target = _user(is_active=True)
    db = FakeSession(target)

    await set_user_active(target.id, UserActiveUpdate(is_active=True), db=db, admin=admin)

    assert db.committed is False


@pytest.mark.asyncio
async def test_missing_user_returns_404() -> None:
    admin = _user(role=UserRole.ADMIN.value)
    db = FakeSession(None)

    with pytest.raises(HTTPException) as exc:
        await set_user_active(uuid4(), UserActiveUpdate(is_active=False), db=db, admin=admin)

    assert exc.value.status_code == 404
