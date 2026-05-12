from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.database import get_db
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.auth import (
    CurrentUserRead,
    MobileAuthResponse,
    MobileLoginRequest,
    MobileRefreshRequest,
    MobileRefreshResponse,
    SessionTokenRead,
)
from app.services.auth_security import hash_token, verify_password
from app.services.auth_sessions import (
    SessionProfile,
    create_session,
    extract_request_metadata,
    rotate_session,
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
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный e-mail или пароль")

    ua, ip = extract_request_metadata(request)
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
    now = utcnow()
    result = await db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.refresh_token_hash == hash_token(payload.refresh_token),
            UserSession.revoked_at.is_(None),
            UserSession.refresh_expires_at > now,
            User.is_active.is_(True),
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-токен недействителен")

    session, user = row
    ua, ip = extract_request_metadata(request)
    credentials = await rotate_session(
        db=db,
        old_session=session,
        user=user,
        profile=SessionProfile.MOBILE,
        user_agent=ua,
        ip_address=ip,
    )
    await db.commit()
    return MobileRefreshResponse(session=_session_payload(credentials))
