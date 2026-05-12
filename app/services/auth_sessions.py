from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.config import settings
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token


class SessionProfile(str, Enum):
    WEB = "web"
    MOBILE = "mobile"


@dataclass(frozen=True)
class SessionCredentials:
    token: str
    expires_at: datetime


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utcnow()).total_seconds()))
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
        path="/",
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )


def _ttl_hours_for(profile: SessionProfile) -> int:
    if profile is SessionProfile.MOBILE:
        return settings.mobile_session_ttl_hours
    return settings.web_session_ttl_hours


async def create_session(
    *,
    db: AsyncSession,
    user: User,
    response: Response | None = None,
    profile: SessionProfile = SessionProfile.WEB,
    set_cookie: bool | None = None,
) -> SessionCredentials:
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(hours=_ttl_hours_for(profile))

    should_set_cookie = (
        set_cookie
        if set_cookie is not None
        else (profile is SessionProfile.WEB and response is not None)
    )

    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=expires_at,
        created_at=utcnow(),
    )
    db.add(session)
    await db.flush()
    if should_set_cookie and response is not None:
        set_session_cookie(response, token, expires_at)
    return SessionCredentials(token=token, expires_at=expires_at)
