from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel

from app.enums import ApplicationStatus


class NotificationRead(BaseModel):
    """Унифицированная нотификация для UI.

    Источники:
    - ApplicationEvent — события заявок (link_type='application', link_id=application_id).
    - UserNotification — чаты и пр. (link_type как сохранено в БД).
    """
    id: UUID
    kind: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None
    # Куда вести при клике
    link_type: Optional[Literal["application", "chat"]] = None
    link_id: Optional[UUID] = None
    # Дополнительный контекст для application-source (опционально)
    application_id: Optional[UUID] = None
    application_status: Optional[ApplicationStatus] = None
    application_title: Optional[str] = None
    # Маркер источника — нужно для mark-read
    source: Literal["application_event", "user_notification"]


class NotificationInboxRead(BaseModel):
    unread_count: int
    items: list[NotificationRead]
