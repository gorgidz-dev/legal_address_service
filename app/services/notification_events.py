from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.enums import ApplicationEventKind, ApplicationStatus, NotificationAudience, UserRole
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.schemas.notification import NotificationRead


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

    # Fan-out to subscribed webhook listeners. Inline enqueue (no HTTP yet — that
    # happens in deliver_pending). Safe to do under the same transaction; webhooks
    # are an opt-in feature and any error here would otherwise mask the real event.
    from app.services.webhooks import dispatch_event  # avoid circular import

    try:
        await dispatch_event(
            db=db,
            event=f"application.{kind.value}",
            data={
                "application_id": str(application_id),
                "kind": kind.value,
                "audience": audience.value,
                "title": title,
                "message": message,
                "payload": payload or {},
            },
        )
    except Exception:  # pragma: no cover — defensive; webhook errors must never break event creation
        pass

    return event


def event_visible_to_role(event: object, role: str) -> bool:
    audience = getattr(event, "audience")
    if audience == "admin":
        return role in {"admin", "manager", "lawyer"}
    return audience == role


def notification_audience_for_user(user: object) -> NotificationAudience:
    try:
        role = UserRole(getattr(user, "role"))
    except ValueError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для уведомлений") from e

    if role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER}:
        return NotificationAudience.ADMIN
    if role == UserRole.CLIENT:
        return NotificationAudience.CLIENT
    return NotificationAudience.OWNER


def notification_visible_to_user(*, event: object, application: object, user: object) -> bool:
    audience = notification_audience_for_user(user)
    if getattr(event, "audience") != audience.value:
        return False

    role = UserRole(getattr(user, "role"))
    if role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER}:
        return True
    if role == UserRole.CLIENT:
        return getattr(application, "created_by") == getattr(user, "id", None)
    if getattr(user, "provider_id", None) is None:
        return False
    return getattr(application, "provider_id") == getattr(user, "provider_id")


def notification_read_from_row(*, event: ApplicationEvent | object, application: Application | object) -> NotificationRead:
    title = (
        getattr(application, "company_name", None)
        or getattr(application, "planned_client_name", None)
        or "Заявка"
    )
    return NotificationRead(
        id=getattr(event, "id"),
        application_id=getattr(event, "application_id"),
        kind=ApplicationEventKind(getattr(event, "kind")),
        audience=NotificationAudience(getattr(event, "audience")),
        title=getattr(event, "title"),
        message=getattr(event, "message"),
        payload=getattr(event, "payload"),
        is_read=getattr(event, "is_read"),
        created_by=getattr(event, "created_by"),
        created_at=getattr(event, "created_at"),
        read_at=getattr(event, "read_at"),
        application_status=ApplicationStatus(getattr(application, "status")),
        application_title=title,
    )


def _base_notification_statement(user: object, *, unread_only: bool = False):
    audience = notification_audience_for_user(user)
    statement = (
        select(ApplicationEvent, Application)
        .join(Application, Application.id == ApplicationEvent.application_id)
        .where(ApplicationEvent.audience == audience.value)
    )

    role = UserRole(getattr(user, "role"))
    if role == UserRole.CLIENT:
        statement = statement.where(Application.created_by == getattr(user, "id", None))
    elif role == UserRole.OWNER:
        provider_id = getattr(user, "provider_id", None)
        if provider_id is None:
            statement = statement.where(False)
        else:
            statement = statement.where(Application.provider_id == provider_id)

    if unread_only:
        statement = statement.where(ApplicationEvent.is_read.is_(False))
    return statement


async def list_user_notifications(
    *,
    db: AsyncSession,
    user: object,
    limit: int = 20,
    unread_only: bool = False,
) -> list[NotificationRead]:
    bounded_limit = max(1, min(limit, 100))
    result = await db.execute(
        _base_notification_statement(user, unread_only=unread_only)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(bounded_limit)
    )
    notifications: list[NotificationRead] = []
    for event, application in result.all():
        if notification_visible_to_user(event=event, application=application, user=user):
            notifications.append(notification_read_from_row(event=event, application=application))
    return notifications


async def count_unread_notifications(*, db: AsyncSession, user: object) -> int:
    rows_statement = _base_notification_statement(user, unread_only=True).subquery()
    result = await db.execute(select(func.count()).select_from(rows_statement))
    return int(result.scalar_one())


async def mark_notification_read(*, db: AsyncSession, event_id: UUID, user: object) -> NotificationRead:
    result = await db.execute(
        _base_notification_statement(user)
        .where(ApplicationEvent.id == event_id)
        .limit(1)
    )
    row = result.first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")

    event, application = row
    if not notification_visible_to_user(event=event, application=application, user=user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")

    if not event.is_read:
        event.is_read = True
        event.read_at = utcnow()
        await db.flush()

    return notification_read_from_row(event=event, application=application)
