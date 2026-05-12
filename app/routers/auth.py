from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
    SessionRead,
)
from app.services.auth_security import (
    hash_password_async,
    hash_token,
    verify_password_async,
)
from app.services.auth_sessions import (
    SessionProfile,
    atomic_consume_refresh,
    create_session,
    delete_session_cookie,
    extract_request_metadata,
)
from app.services.rate_limit import (
    INVITATION_ACCEPT_RULES,
    LOGIN_RULES,
    assert_within_rate_limit,
    record_attempt,
)
from app.services.user_create import try_persist_user

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
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    result = await db.execute(select(func.count()).select_from(User))
    if int(result.scalar_one()) != 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Первый администратор уже создан")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=await hash_password_async(payload.password),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    if not await try_persist_user(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Первый администратор уже создан")
    ua, ip = extract_request_metadata(request)
    await create_session(db=db, user=user, response=response, user_agent=ua, ip_address=ip)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    ua, ip = extract_request_metadata(request)
    email = payload.email.lower()
    keys = {"email": email, "ip": ip}

    await assert_within_rate_limit(db, LOGIN_RULES, keys)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    succeeded = bool(
        user is not None
        and user.is_active
        and await verify_password_async(payload.password, user.password_hash)
    )
    await record_attempt(db, "login", keys, succeeded=succeeded)

    if not succeeded:
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный e-mail или пароль")

    await create_session(db=db, user=user, response=response, user_agent=ua, ip_address=ip)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))


@router.post("/refresh", response_model=AuthResponse)
async def refresh_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нет refresh-токена")

    revoked = await atomic_consume_refresh(db, token)
    if revoked is None:
        delete_session_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh-токен недействителен")

    user = await db.get(User, revoked.user_id)
    if user is None or not user.is_active:
        delete_session_cookie(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь недоступен")

    ua, ip = extract_request_metadata(request)
    await create_session(
        db=db,
        user=user,
        response=response,
        profile=SessionProfile.WEB,
        user_agent=ua,
        ip_address=ip,
        device_name=revoked.device_name,
    )
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Logout current device only."""
    session_id = getattr(request.state, "session_id", None)
    if session_id is not None:
        current = await db.get(UserSession, session_id)
        if current is not None and current.user_id == user.id and current.revoked_at is None:
            current.revoked_at = utcnow()
            await db.commit()
    delete_session_cookie(response)
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_others(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Logout every session of this user except the current one."""
    current_id = getattr(request.state, "session_id", None)
    now = utcnow()
    stmt = select(UserSession).where(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at > now,
    )
    if current_id is not None:
        stmt = stmt.where(UserSession.id != current_id)
    result = await db.execute(stmt)
    for session in result.scalars().all():
        session.revoked_at = now
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionRead])
async def list_my_sessions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SessionRead]:
    now = utcnow()
    current_id = getattr(request.state, "session_id", None)
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    )
    return [
        SessionRead(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            refresh_expires_at=s.refresh_expires_at,
            last_refreshed_at=s.last_refreshed_at,
            last_seen_at=s.last_seen_at,
            session_type=s.session_type,
            device_name=s.device_name,
            user_agent=s.user_agent,
            ip_address=s.ip_address,
            is_current=(s.id == current_id),
        )
        for s in result.scalars().all()
    ]


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
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    ua, ip = extract_request_metadata(request)
    keys = {"ip": ip}
    await assert_within_rate_limit(db, INVITATION_ACCEPT_RULES, keys)

    async def _fail(http_exc: HTTPException) -> None:
        await record_attempt(db, "invitation_accept", keys, succeeded=False)
        await db.commit()
        raise http_exc

    result = await db.execute(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    invitation = result.scalar_one_or_none()
    if invitation is None:
        await _fail(HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение не найдено"))
    if invitation.accepted_at is not None:
        await _fail(HTTPException(status.HTTP_409_CONFLICT, "Приглашение уже использовано"))
    if invitation.expires_at <= utcnow():
        await _fail(HTTPException(status.HTTP_409_CONFLICT, "Срок приглашения истёк"))

    existing = await db.execute(select(User).where(User.email == invitation.email))
    if existing.scalar_one_or_none() is not None:
        await _fail(HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует"))

    user = User(
        email=invitation.email,
        full_name=payload.full_name or invitation.full_name or invitation.email,
        password_hash=await hash_password_async(payload.password),
        role=invitation.role,
        is_active=True,
    )
    invitation.accepted_at = utcnow()
    if not await try_persist_user(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    await create_session(db=db, user=user, response=response, user_agent=ua, ip_address=ip)
    await record_attempt(db, "invitation_accept", keys, succeeded=True)
    await db.commit()
    await db.refresh(user)
    return AuthResponse(user=CurrentUserRead.model_validate(user))
