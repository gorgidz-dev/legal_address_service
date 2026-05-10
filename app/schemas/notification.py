from __future__ import annotations

from app.enums import ApplicationStatus
from app.schemas.marketplace import ApplicationEventRead
from pydantic import BaseModel


class NotificationRead(ApplicationEventRead):
    application_status: ApplicationStatus
    application_title: str


class NotificationInboxRead(BaseModel):
    unread_count: int
    items: list[NotificationRead]
