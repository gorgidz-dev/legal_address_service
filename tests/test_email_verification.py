"""Подтверждение e-mail: выдача токена, подтверждение, сроки и защита."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.auth import utcnow
from app.main import _is_public_path
from app.services.auth_security import hash_token
from app.services.email_verification import (
    RESEND_COOLDOWN,
    TOKEN_TTL,
    can_resend,
    confirm_verification,
    issue_verification,
    verification_path,
)


def _user(**overrides):
    base = dict(
        id=uuid4(),
        email="client@example.com",
        full_name="Иванов Иван",
        email_verified_at=None,
        email_verification_token_hash=None,
        email_verification_sent_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class FakeSession:
    """Замена AsyncSession: отдаёт заранее подготовленного пользователя."""

    def __init__(self, user=None):
        self._user = user
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, _statement):
        user = self._user

        class Result:
            def scalar_one_or_none(self):
                return user

        return Result()


@pytest.mark.asyncio
async def test_issue_stores_only_hash_of_token() -> None:
    """В базе не должно быть самого токена: утечка дампа не должна давать
    возможности подтвердить чужой адрес."""
    user = _user()
    db = FakeSession(user)

    token = await issue_verification(db, user, send=False)

    assert token
    assert user.email_verification_token_hash == hash_token(token)
    assert user.email_verification_token_hash != token
    assert user.email_verification_sent_at is not None


@pytest.mark.asyncio
async def test_issue_is_noop_for_verified_user() -> None:
    user = _user(email_verified_at=utcnow())
    db = FakeSession(user)

    assert await issue_verification(db, user, send=False) is None
    assert user.email_verification_token_hash is None


@pytest.mark.asyncio
async def test_confirm_marks_verified_and_burns_token() -> None:
    user = _user()
    db = FakeSession(user)
    token = await issue_verification(db, user, send=False)

    result = await confirm_verification(db, token)

    assert result.ok is True
    assert result.already is False
    assert user.email_verified_at is not None
    # Токен одноразовый: хеш стирается, повторный переход по ссылке не сработает.
    assert user.email_verification_token_hash is None


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_token() -> None:
    db = FakeSession(None)
    result = await confirm_verification(db, "какой-то-левый-токен")
    assert result.ok is False


@pytest.mark.asyncio
@pytest.mark.parametrize("token", ["", "   ", None])
async def test_confirm_rejects_empty_token(token) -> None:
    db = FakeSession(None)
    result = await confirm_verification(db, token or "")
    assert result.ok is False


@pytest.mark.asyncio
async def test_expired_link_is_rejected() -> None:
    user = _user()
    db = FakeSession(user)
    token = await issue_verification(db, user, send=False)
    # Отматываем момент отправки за границу срока действия.
    user.email_verification_sent_at = utcnow() - TOKEN_TTL - timedelta(minutes=1)

    result = await confirm_verification(db, token)

    assert result.ok is False
    assert "истёк" in result.reason.lower()
    assert user.email_verified_at is None


@pytest.mark.asyncio
async def test_second_confirm_reports_already_verified() -> None:
    """Человек может открыть ссылку дважды — это не ошибка."""
    user = _user()
    db = FakeSession(user)
    token = await issue_verification(db, user, send=False)
    user.email_verified_at = utcnow()

    result = await confirm_verification(db, token)

    assert result.ok is True
    assert result.already is True


def test_resend_cooldown_blocks_immediate_repeat() -> None:
    """Иначе кнопкой «отправить ещё раз» можно засыпать чужой ящик."""
    fresh = _user(email_verification_sent_at=utcnow())
    assert can_resend(fresh) is False

    old = _user(email_verification_sent_at=utcnow() - RESEND_COOLDOWN - timedelta(seconds=1))
    assert can_resend(old) is True

    never = _user()
    assert can_resend(never) is True


def test_confirm_endpoint_is_public_but_request_is_not() -> None:
    """Ссылку из письма открывают в браузере без сессии — подтверждение
    обязано работать анонимно. А переотправка требует входа."""
    assert _is_public_path("/api/v1/auth/email/verify/confirm", "POST") is True
    assert _is_public_path("/api/v1/auth/email/verify/request", "POST") is False


def test_verification_path_shape() -> None:
    assert verification_path("abc").startswith("/verify/")
