from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.models.auth_attempt import AuthAttempt


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    key_type: str  # 'email' | 'ip'
    window: timedelta
    max_count: int
    count_only_failures: bool = False


LOGIN_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule("login", "email", timedelta(minutes=15), 5, count_only_failures=True),
    RateLimitRule("login", "ip", timedelta(minutes=15), 20, count_only_failures=True),
)

MOBILE_LOGIN_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule("mobile_login", "email", timedelta(minutes=15), 5, count_only_failures=True),
    RateLimitRule("mobile_login", "ip", timedelta(minutes=15), 20, count_only_failures=True),
)

INVITATION_ACCEPT_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule("invitation_accept", "ip", timedelta(minutes=15), 10),
)

PROVIDER_REQUEST_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule("provider_request", "ip", timedelta(hours=1), 5),
)

PUBLIC_APPLICATION_RULES: tuple[RateLimitRule, ...] = (
    RateLimitRule("public_application", "ip", timedelta(hours=1), 10),
)


def _too_many(retry_after_seconds: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Слишком много попыток. Повторите позже.",
        headers={"Retry-After": str(retry_after_seconds)},
    )


async def _count_attempts(
    db: AsyncSession,
    rule: RateLimitRule,
    key: str,
) -> int:
    since = utcnow() - rule.window
    stmt = (
        select(func.count())
        .select_from(AuthAttempt)
        .where(
            AuthAttempt.scope == rule.scope,
            AuthAttempt.key_type == rule.key_type,
            AuthAttempt.attempt_key == key,
            AuthAttempt.created_at >= since,
        )
    )
    if rule.count_only_failures:
        stmt = stmt.where(AuthAttempt.succeeded.is_(False))
    result = await db.execute(stmt)
    return int(result.scalar_one())


async def assert_within_rate_limit(
    db: AsyncSession,
    rules: tuple[RateLimitRule, ...],
    keys: dict[str, str | None],
) -> None:
    """Raise 429 if any rule is exceeded. `keys` maps key_type -> value (None skips)."""
    for rule in rules:
        key = keys.get(rule.key_type)
        if not key:
            continue
        count = await _count_attempts(db, rule, key)
        if count >= rule.max_count:
            raise _too_many(int(rule.window.total_seconds()))


async def record_attempt(
    db: AsyncSession,
    scope: str,
    keys: dict[str, str | None],
    succeeded: bool,
) -> None:
    for key_type, key in keys.items():
        if not key:
            continue
        db.add(
            AuthAttempt(
                scope=scope,
                key_type=key_type,
                attempt_key=key,
                succeeded=succeeded,
            )
        )
    await db.flush()
