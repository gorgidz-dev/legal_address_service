from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import UserRole
from app.models.user import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден или отключён")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль администратора")
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in {UserRole.MANAGER.value, UserRole.LAWYER.value, UserRole.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль менеджера, юриста или администратора")
    return user


async def require_client(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.CLIENT.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль клиента")
    return user


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
