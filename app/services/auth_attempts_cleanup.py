from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.models.auth_attempt import AuthAttempt


DEFAULT_RETENTION = timedelta(hours=24)


async def cleanup_auth_attempts(
    db: AsyncSession,
    retention: timedelta = DEFAULT_RETENTION,
) -> int:
    """Delete auth_attempts older than `retention`. Returns rows affected."""
    cutoff = utcnow() - retention
    result = await db.execute(
        delete(AuthAttempt).where(AuthAttempt.created_at < cutoff)
    )
    return int(result.rowcount or 0)
