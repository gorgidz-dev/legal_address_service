from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.notification import NotificationInboxRead, NotificationRead
from app.services.notification_events import (
    count_unread_notifications,
    list_user_notifications,
    mark_notification_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationInboxRead)
async def get_notification_inbox(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationInboxRead:
    items = await list_user_notifications(db=db, user=user, limit=limit, unread_only=unread_only)
    unread_count = await count_unread_notifications(db=db, user=user)
    return NotificationInboxRead(unread_count=unread_count, items=items)


@router.post("/{event_id}/read", response_model=NotificationRead)
async def mark_notification_as_read(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationRead:
    notification = await mark_notification_read(db=db, event_id=event_id, user=user)
    await db.commit()
    return notification
