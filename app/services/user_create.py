from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def try_persist_user(db: AsyncSession, user: User) -> bool:
    """Insert a User, returning True on success.

    Returns False if a concurrent request inserted the same email between our
    pre-check and our flush — the DB's unique index on users.email raises
    IntegrityError. Caller should map that to 409.

    A SELECT-then-INSERT pre-check alone is racy: two parallel signups for the
    same email both see "no row" and both INSERT. Without this guard, the loser
    gets a 500 IntegrityError leaked to the client.
    """
    db.add(user)
    try:
        await db.flush()
        return True
    except IntegrityError:
        await db.rollback()
        return False
