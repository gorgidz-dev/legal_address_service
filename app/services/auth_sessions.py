from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from fastapi import Request, Response
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
    refresh_token: str
    refresh_expires_at: datetime


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.session_cookie_secure,
        "samesite": settings.session_cookie_samesite,
        "domain": settings.session_cookie_domain,
    }


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utcnow()).total_seconds()))
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        path="/",
        **_cookie_kwargs(),
    )


def set_refresh_cookie(response: Response, token: str, expires_at: datetime) -> None:
    max_age = max(0, int((expires_at - utcnow()).total_seconds()))
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=max_age,
        path=settings.refresh_cookie_path,
        **_cookie_kwargs(),
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
    )
    response.delete_cookie(
        settings.refresh_cookie_name,
        path=settings.refresh_cookie_path,
        domain=settings.session_cookie_domain,
    )


def _access_ttl_hours(profile: SessionProfile) -> int:
    if profile is SessionProfile.MOBILE:
        return settings.mobile_session_ttl_hours
    return settings.web_session_ttl_hours


def _refresh_ttl_hours(profile: SessionProfile) -> int:
    if profile is SessionProfile.MOBILE:
        return settings.mobile_refresh_ttl_hours
    return settings.web_refresh_ttl_hours


_USER_AGENT_MAX = 500
_DEVICE_NAME_MAX = 200
LAST_SEEN_THROTTLE = timedelta(minutes=5)


def extract_request_metadata(request: Request) -> tuple[str | None, str | None]:
    """Return (user_agent, ip_address) from incoming request."""
    ua = request.headers.get("user-agent")
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else None
    return ua, ip


def should_update_last_seen(session: UserSession, now: datetime) -> bool:
    if session.last_seen_at is None:
        return True
    return (now - session.last_seen_at) >= LAST_SEEN_THROTTLE


def _trim(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:limit] if value else None


async def create_session(
    *,
    db: AsyncSession,
    user: User,
    response: Response | None = None,
    profile: SessionProfile = SessionProfile.WEB,
    set_cookie: bool | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
    device_name: str | None = None,
) -> SessionCredentials:
    now = utcnow()
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(48)
    access_expires_at = now + timedelta(hours=_access_ttl_hours(profile))
    refresh_expires_at = now + timedelta(hours=_refresh_ttl_hours(profile))

    should_set_cookie = (
        set_cookie
        if set_cookie is not None
        else (profile is SessionProfile.WEB and response is not None)
    )

    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(access_token),
        expires_at=access_expires_at,
        refresh_token_hash=hash_token(refresh_token),
        refresh_expires_at=refresh_expires_at,
        created_at=now,
        session_type=profile.value,
        device_name=_trim(device_name, _DEVICE_NAME_MAX),
        user_agent=_trim(user_agent, _USER_AGENT_MAX),
        ip_address=_trim(ip_address, 64),
        last_seen_at=now,
    )
    db.add(session)
    await db.flush()

    if should_set_cookie and response is not None:
        set_session_cookie(response, access_token, access_expires_at)
        set_refresh_cookie(response, refresh_token, refresh_expires_at)

    return SessionCredentials(
        token=access_token,
        expires_at=access_expires_at,
        refresh_token=refresh_token,
        refresh_expires_at=refresh_expires_at,
    )


async def rotate_session(
    *,
    db: AsyncSession,
    old_session: UserSession,
    user: User,
    response: Response | None = None,
    profile: SessionProfile = SessionProfile.WEB,
    set_cookie: bool | None = None,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> SessionCredentials:
    """Rotate-on-use: revoke old session, issue fresh pair (carries forward device_name)."""
    old_session.revoked_at = utcnow()
    old_session.last_refreshed_at = utcnow()
    await db.flush()
    return await create_session(
        db=db,
        user=user,
        response=response,
        profile=profile,
        set_cookie=set_cookie,
        user_agent=user_agent,
        ip_address=ip_address,
        device_name=old_session.device_name,
    )
