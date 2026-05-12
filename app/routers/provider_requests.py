from __future__ import annotations

"""Админская очередь заявок собственников: просмотр, перевод в работу, одобрение, отклонение."""
import secrets
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, utcnow
from app.config import settings
from app.database import get_db
from app.enums import OwnerConnectionRequestStatus, UserRole
from app.models.invitation import Invitation
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.user import User
from app.schemas.marketplace import (
    ProviderConnectionRequestApprove,
    ProviderConnectionRequestApproveResult,
    ProviderConnectionRequestRead,
    ProviderConnectionRequestStatusUpdate,
)
from app.services.auth_security import hash_token

router = APIRouter(
    prefix="/admin/provider-requests",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[ProviderConnectionRequestRead])
async def list_provider_requests(
    request_status: Optional[OwnerConnectionRequestStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[ProviderConnectionRequest]:
    stmt = select(ProviderConnectionRequest).order_by(ProviderConnectionRequest.created_at.desc())
    if request_status is not None:
        stmt = stmt.where(ProviderConnectionRequest.status == request_status.value)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{request_id}", response_model=ProviderConnectionRequestRead)
async def get_provider_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ProviderConnectionRequest:
    request = await db.get(ProviderConnectionRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    return request


@router.patch("/{request_id}", response_model=ProviderConnectionRequestRead)
async def update_provider_request_status(
    request_id: UUID,
    payload: ProviderConnectionRequestStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ProviderConnectionRequest:
    request = await db.get(ProviderConnectionRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")

    new_status = payload.status
    current = OwnerConnectionRequestStatus(request.status)
    _assert_transition_allowed(current, new_status)

    request.status = new_status.value
    if payload.admin_comment is not None:
        request.admin_comment = payload.admin_comment
    request.reviewed_by = admin.id
    request.reviewed_at = utcnow()
    await db.commit()
    await db.refresh(request)
    return request


@router.post(
    "/{request_id}/approve",
    response_model=ProviderConnectionRequestApproveResult,
    status_code=status.HTTP_201_CREATED,
)
async def approve_provider_request(
    request_id: UUID,
    payload: ProviderConnectionRequestApprove,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ProviderConnectionRequestApproveResult:
    request = await db.get(ProviderConnectionRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")

    current = OwnerConnectionRequestStatus(request.status)
    _assert_transition_allowed(current, OwnerConnectionRequestStatus.INVITED)

    existing_user = await db.execute(select(User).where(User.email == request.contact_email))
    if existing_user.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Пользователь с таким e-mail уже зарегистрирован",
        )

    provider = Provider(
        code=payload.code,
        short_name=payload.short_name,
        full_name=payload.full_name,
        phone=request.contact_phone,
        is_active=True,
    )
    db.add(provider)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Не удалось создать собственника: {e.orig}",
        ) from e

    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(hours=settings.invitation_ttl_hours)
    invitation = Invitation(
        email=request.contact_email,
        full_name=request.contact_name,
        role=UserRole.OWNER.value,
        token_hash=hash_token(token),
        expires_at=expires_at,
        created_at=utcnow(),
        created_by=admin.id,
        provider_id=provider.id,
        source_request_id=request.id,
    )
    db.add(invitation)
    await db.flush()

    request.status = OwnerConnectionRequestStatus.INVITED.value
    request.reviewed_by = admin.id
    request.reviewed_at = utcnow()
    request.invitation_id = invitation.id
    if payload.admin_comment is not None:
        request.admin_comment = payload.admin_comment

    await db.commit()
    await db.refresh(request)

    return ProviderConnectionRequestApproveResult(
        request=ProviderConnectionRequestRead.model_validate(request),
        provider_id=provider.id,
        invitation_id=invitation.id,
        invitation_token=token,
        invitation_path=f"/invite/{token}",
        invitation_expires_at=expires_at,
    )


def _assert_transition_allowed(
    current: OwnerConnectionRequestStatus,
    target: OwnerConnectionRequestStatus,
) -> None:
    """new ⇄ reviewing; new/reviewing → invited|rejected; invited/rejected — терминальные."""
    if current == target:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Заявка уже в статусе {current.value}")
    terminal = {OwnerConnectionRequestStatus.INVITED, OwnerConnectionRequestStatus.REJECTED}
    if current in terminal:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Заявка уже в терминальном статусе {current.value}",
        )
