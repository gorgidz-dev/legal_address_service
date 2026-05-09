from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.config import settings
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token


@dataclass(frozen=True)
class SessionCredentials:
    token: str
    expires_at: datetime


def set_session_cookie(response: Response, token: str, expires_at) -> None:
    max_age = max(0, int((expires_at - utcnow()).total_seconds()))
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


async def create_session(
    *,
    db: AsyncSession,
    user: User,
    response: Response | None = None,
    set_cookie: bool = True,
) -> SessionCredentials:
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(hours=settings.session_ttl_hours)
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=expires_at,
        created_at=utcnow(),
    )
    db.add(session)
    await db.flush()
    if response is not None and set_cookie:
        set_session_cookie(response, token, expires_at)
    return SessionCredentials(token=token, expires_at=expires_at)
