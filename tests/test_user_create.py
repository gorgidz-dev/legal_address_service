from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.enums import UserRole
from app.models.user import User
from app.services.user_create import try_persist_user


class _FakeDB:
    def __init__(self, *, raise_integrity: bool = False) -> None:
        self.added: list[object] = []
        self.flushed = False
        self.rolled_back = False
        self._raise = raise_integrity

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        if self._raise:
            raise IntegrityError("INSERT failed", params=None, orig=Exception("duplicate key"))
        self.flushed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _make_user() -> User:
    user = User(
        email="a@b.c",
        full_name="Test",
        password_hash="pbkdf2_sha256$1$x$y",
        role=UserRole.CLIENT.value,
        is_active=True,
    )
    user.id = uuid4()
    return user


@pytest.mark.asyncio
async def test_try_persist_user_success() -> None:
    db = _FakeDB()
    ok = await try_persist_user(db, _make_user())
    assert ok is True
    assert db.flushed
    assert not db.rolled_back
    assert len(db.added) == 1


@pytest.mark.asyncio
async def test_try_persist_user_collision_returns_false_and_rolls_back() -> None:
    db = _FakeDB(raise_integrity=True)
    ok = await try_persist_user(db, _make_user())
    assert ok is False
    assert db.rolled_back is True
