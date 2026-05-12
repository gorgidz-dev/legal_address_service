from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.auth_attempt import AuthAttempt
from app.services.rate_limit import (
    LOGIN_RULES,
    RateLimitRule,
    assert_within_rate_limit,
    record_attempt,
)


def _now():
    return datetime.now(timezone.utc)


class _FakeDB:
    """Minimal in-memory stand-in evaluating the WHERE clause Python-side."""

    def __init__(self) -> None:
        self.rows: list[AuthAttempt] = []
        self.committed = False
        self._filter = None

    def add(self, item) -> None:
        if isinstance(item, AuthAttempt):
            if item.created_at is None:
                item.created_at = _now()
            self.rows.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def execute(self, stmt):
        # Walk the WHERE clauses to extract scope/key_type/attempt_key/created_at filter
        scope = key_type = attempt_key = None
        since = None
        only_failures = False
        for clause in stmt.whereclause.clauses if hasattr(stmt.whereclause, "clauses") else [stmt.whereclause]:
            text = str(clause)
            if "scope = " in text:
                scope = clause.right.value
            elif "key_type = " in text:
                key_type = clause.right.value
            elif "attempt_key = " in text:
                attempt_key = clause.right.value
            elif "created_at >= " in text:
                since = clause.right.value
            elif "succeeded IS false" in text or "succeeded = false" in text:
                only_failures = True

        def keep(row: AuthAttempt) -> bool:
            if scope is not None and row.scope != scope:
                return False
            if key_type is not None and row.key_type != key_type:
                return False
            if attempt_key is not None and row.attempt_key != attempt_key:
                return False
            if since is not None and row.created_at < since:
                return False
            if only_failures and row.succeeded:
                return False
            return True

        matched = [r for r in self.rows if keep(r)]

        class _R:
            def scalar_one(self_inner):
                return len(matched)

        return _R()


@pytest.mark.asyncio
async def test_record_attempt_persists_for_each_key_type() -> None:
    db = _FakeDB()
    await record_attempt(db, "login", {"email": "a@b.c", "ip": "1.2.3.4"}, succeeded=False)
    assert len(db.rows) == 2
    scopes = {(r.scope, r.key_type, r.attempt_key) for r in db.rows}
    assert ("login", "email", "a@b.c") in scopes
    assert ("login", "ip", "1.2.3.4") in scopes


@pytest.mark.asyncio
async def test_record_attempt_skips_none_keys() -> None:
    db = _FakeDB()
    await record_attempt(db, "login", {"email": "a@b.c", "ip": None}, succeeded=True)
    assert len(db.rows) == 1
    assert db.rows[0].key_type == "email"


@pytest.mark.asyncio
async def test_assert_within_rate_limit_raises_at_threshold() -> None:
    db = _FakeDB()
    rule = RateLimitRule("login", "email", timedelta(minutes=15), 3, count_only_failures=True)
    for _ in range(3):
        await record_attempt(db, "login", {"email": "a@b.c"}, succeeded=False)

    with pytest.raises(HTTPException) as info:
        await assert_within_rate_limit(db, (rule,), {"email": "a@b.c"})
    assert info.value.status_code == 429
    assert "Retry-After" in info.value.headers


@pytest.mark.asyncio
async def test_assert_within_rate_limit_passes_below_threshold() -> None:
    db = _FakeDB()
    rule = RateLimitRule("login", "email", timedelta(minutes=15), 5, count_only_failures=True)
    for _ in range(4):
        await record_attempt(db, "login", {"email": "a@b.c"}, succeeded=False)

    # 4 < 5, should pass
    await assert_within_rate_limit(db, (rule,), {"email": "a@b.c"})


@pytest.mark.asyncio
async def test_count_only_failures_ignores_successful_attempts() -> None:
    db = _FakeDB()
    rule = RateLimitRule("login", "email", timedelta(minutes=15), 3, count_only_failures=True)
    for _ in range(10):
        await record_attempt(db, "login", {"email": "a@b.c"}, succeeded=True)
    # 0 failures — still within limit
    await assert_within_rate_limit(db, (rule,), {"email": "a@b.c"})


@pytest.mark.asyncio
async def test_old_attempts_outside_window_are_ignored() -> None:
    db = _FakeDB()
    long_ago = _now() - timedelta(hours=2)
    for _ in range(5):
        db.rows.append(
            AuthAttempt(
                scope="login",
                key_type="email",
                attempt_key="a@b.c",
                succeeded=False,
                created_at=long_ago,
            )
        )
    rule = RateLimitRule("login", "email", timedelta(minutes=15), 3, count_only_failures=True)
    await assert_within_rate_limit(db, (rule,), {"email": "a@b.c"})


@pytest.mark.asyncio
async def test_login_rules_constants_are_sensible() -> None:
    assert any(r.key_type == "email" for r in LOGIN_RULES)
    assert any(r.key_type == "ip" for r in LOGIN_RULES)
