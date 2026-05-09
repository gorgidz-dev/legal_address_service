from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.enums import ApplicationEventKind, NotificationAudience
from app.models.application_event import ApplicationEvent


def event_values(
    *,
    application_id: UUID,
    kind: ApplicationEventKind,
    audience: NotificationAudience,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    return {
        "application_id": application_id,
        "kind": kind.value,
        "audience": audience.value,
        "title": title,
        "message": message,
        "payload": payload or {},
        "created_by": created_by,
        "created_at": utcnow(),
    }


async def create_application_event(
    *,
    db: AsyncSession,
    application_id: UUID,
    kind: ApplicationEventKind,
    audience: NotificationAudience,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
    created_by: UUID | None = None,
) -> ApplicationEvent:
    event = ApplicationEvent(
        **event_values(
            application_id=application_id,
            kind=kind,
            audience=audience,
            title=title,
            message=message,
            payload=payload,
            created_by=created_by,
        )
    )
    db.add(event)
    await db.flush()
    return event


def event_visible_to_role(event: object, role: str) -> bool:
    audience = getattr(event, "audience")
    if audience == "admin":
        return role in {"admin", "manager", "lawyer"}
    return audience == role
