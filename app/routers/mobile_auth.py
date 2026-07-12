from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    CurrentUserRead,
    MobileAuthResponse,
    MobileLoginRequest,
    MobileRefreshRequest,
    MobileRefreshResponse,
    SessionTokenRead,
)
from app.services.auth_security import verify_password_async
from app.services.auth_sessions import (
    SessionProfile,
    atomic_consume_refresh,
    create_session,
    extract_request_metadata,
)
from app.services.rate_limit import (
    MOBILE_LOGIN_RULES,
    assert_within_rate_limit,
    record_attempt,
)

router = APIRouter(prefix="/mobile/auth", tags=["mobile-auth"])


def _session_payload(credentials) -> SessionTokenRead:
    return SessionTokenRead(
        access_token=credentials.token,
        expires_at=credentials.expires_at,
        refresh_token=credentials.refresh_token,
        refresh_expires_at=credentials.refresh_expires_at,
    )


@router.post("/login", response_model=MobileAuthResponse)
async def mobile_login(
    payload: MobileLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MobileAuthResponse:
    ua, ip = extract_request_metadata(request)
    email = payload.email.lower()
    keys = {"email": email, "ip": ip}

    await assert_within_rate_limit(db, MOBILE_LOGIN_RULES, keys)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    succeeded = bool(
        user is not None
        and user.is_active
        and await verify_password_async(payload.password, user.password_hash)
    )
    await record_attempt(db, "mobile_login", keys, succeeded=succeeded)

    if not succeeded:
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный e-mail или пароль")

    credentials = await create_session(
        db=db,
        user=user,
        profile=SessionProfile.MOBILE,
        user_agent=ua,
        ip_address=ip,
        device_name=payload.device_name,
    )
    await db.commit()
    await db.refresh(user)
    return MobileAuthResponse(
        user=CurrentUserRead.model_validate(user),
        session=_session_payload(credentials),
    )


@router.post("/refresh", response_model=MobileRefreshResponse)
async def mobile_refresh(
    payload: MobileRefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> MobileRefreshResponse:
    revoked = await atomic_consume_refresh(db, payload.refresh_token)
    if revoked is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-токен недействителен")

    user = await db.get(User, revoked.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь недоступен")

    ua, ip = extract_request_metadata(request)
    credentials = await create_session(
        db=db,
        user=user,
        profile=SessionProfile.MOBILE,
        user_agent=ua,
        ip_address=ip,
        device_name=revoked.device_name,
    )
    await db.commit()
    return MobileRefreshResponse(session=_session_payload(credentials))
