from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.auth import CurrentUserRead, LoginRequest, MobileAuthResponse, SessionTokenRead
from app.services.auth_security import verify_password
from app.services.auth_sessions import create_session

router = APIRouter(prefix="/mobile/auth", tags=["mobile-auth"])


@router.post("/login", response_model=MobileAuthResponse)
async def mobile_login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> MobileAuthResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный e-mail или пароль")

    credentials = await create_session(db=db, user=user, set_cookie=False)
    await db.commit()
    await db.refresh(user)
    return MobileAuthResponse(
        user=CurrentUserRead.model_validate(user),
        session=SessionTokenRead(
            access_token=credentials.token,
            expires_at=credentials.expires_at,
        ),
    )
