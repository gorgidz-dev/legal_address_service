from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin, utcnow
from app.config import settings
from app.database import get_db
from app.enums import UserRole
from app.models.invitation import Invitation
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.auth import (
    AuthResponse,
    BootstrapAdminRequest,
    BootstrapState,
    CurrentUserRead,
    InvitationAccept,
    InvitationCreate,
    InvitationCreateResult,
    InvitationRead,
    LoginRequest,
)
from app.services.auth_security import hash_password, hash_token, verify_password
from app.services.auth_sessions import create_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/bootstrap-state", response_model=BootstrapState)
async def bootstrap_state(db: AsyncSession = Depends(get_db)) -> BootstrapState:
    result = await db.execute(select(func.count()).select_from(User))
    return BootstrapState(can_bootstrap=int(result.scalar_one()) == 0)


@router.post(
    "/bootstrap-admin",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_admin(
    payload: BootstrapAdminRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(func.count()).select_from(User))
    if int(result.scalar_one()) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Первый администратор уже создан")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await create_session(db=db, user=user, response=response)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный e-mail или пароль")

    await create_session(db=db, user=user, response=response)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    now = utcnow()
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    for session in result.scalars().all():
        session.revoked_at = now
    await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response


@router.get("/me", response_model=CurrentUserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/invitations", response_model=list[InvitationRead])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Invitation]:
    result = await db.execute(select(Invitation).order_by(Invitation.created_at.desc()))
    return list(result.scalars().all())


@router.post(
    "/invitations",
    response_model=InvitationCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> InvitationCreateResult:
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        email=payload.email.lower(),
        full_name=payload.full_name,
        role=payload.role.value,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(hours=settings.invitation_ttl_hours),
        created_at=utcnow(),
        created_by=admin.id,
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return InvitationCreateResult(
        id=invitation.id,
        email=invitation.email,
        full_name=invitation.full_name,
        role=invitation.role,
        expires_at=invitation.expires_at,
        accepted_at=invitation.accepted_at,
        invitation_token=token,
        invitation_path=f"/invite/{token}",
    )


@router.post("/invitations/{token}/accept", response_model=AuthResponse)
async def accept_invitation(
    token: str,
    payload: InvitationAccept,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено")
    if invitation.accepted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Приглашение уже использовано")
    if invitation.expires_at <= utcnow():
        raise HTTPException(status.HTTP_409_CONFLICT, "Срок приглашения истёк")

    existing = await db.execute(select(User).where(User.email == invitation.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")

    user = User(
        email=invitation.email,
        full_name=payload.full_name or invitation.full_name or invitation.email,
        password_hash=hash_password(payload.password),
        role=invitation.role,
        is_active=True,
    )
    invitation.accepted_at = utcnow()
    db.add(user)
    await db.flush()
    await create_session(db=db, user=user, response=response)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))
