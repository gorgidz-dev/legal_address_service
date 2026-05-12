from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.auth_attempt import AuthAttempt
from app.services.auth_attempts_cleanup import cleanup_auth_attempts


def _now():
    return datetime.now(timezone.utc)


class _FakeDB:
    def __init__(self, rows: list[AuthAttempt]):
        self.rows = rows
        self.committed = False

    async def execute(self, stmt):
        cutoff = None
        # walk WHERE for created_at < value
        clause = stmt.whereclause
        clauses = clause.clauses if hasattr(clause, "clauses") else [clause]
        for c in clauses:
            if "created_at < " in str(c):
                cutoff = c.right.value

        before = len(self.rows)
        if cutoff is not None:
            self.rows = [r for r in self.rows if r.created_at >= cutoff]
        deleted = before - len(self.rows)

        class _R:
            rowcount = deleted

        return _R()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_cleanup_deletes_only_older_than_retention() -> None:
    now = _now()
    fresh = AuthAttempt(
        scope="login",
        key_type="email",
        attempt_key="a@b.c",
        succeeded=False,
        created_at=now - timedelta(hours=1),
    )
    stale = AuthAttempt(
        scope="login",
        key_type="email",
        attempt_key="a@b.c",
        succeeded=False,
        created_at=now - timedelta(hours=48),
    )
    db = _FakeDB([fresh, stale])

    deleted = await cleanup_auth_attempts(db, retention=timedelta(hours=24))

    assert deleted == 1
    assert db.rows == [fresh]


@pytest.mark.asyncio
async def test_cleanup_returns_zero_when_nothing_to_delete() -> None:
    db = _FakeDB([])
    assert await cleanup_auth_attempts(db, retention=timedelta(hours=24)) == 0
