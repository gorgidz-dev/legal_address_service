from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.enums import ApplicationEventKind, ApplicationStatus, NotificationAudience, UserRole
from app.models.address import Address
from app.models.address_chat import AddressChat
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.user import User
from app.models.user_notification import UserNotification
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
    application_id = getattr(event, "application_id")
    return NotificationRead(
        id=getattr(event, "id"),
        kind=getattr(event, "kind"),
        title=getattr(event, "title"),
        message=getattr(event, "message"),
        is_read=getattr(event, "is_read"),
        created_at=getattr(event, "created_at"),
        read_at=getattr(event, "read_at"),
        link_type="application",
        link_id=application_id,
        application_id=application_id,
        application_status=ApplicationStatus(getattr(application, "status")),
        application_title=title,
        source="application_event",
    )


def notification_read_from_user_row(n: UserNotification) -> NotificationRead:
    return NotificationRead(
        id=n.id,
        kind=n.kind,
        title=n.title,
        message=n.body,
        is_read=n.is_read,
        created_at=n.created_at,
        read_at=n.read_at,
        link_type=n.link_type,
        link_id=n.link_id,
        source="user_notification",
    )


_STAFF_ROLES = {UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER}


async def _user_can_access_link(
    db: AsyncSession, *, user_id: UUID, link_type: str, link_id: UUID
) -> bool:
    """Имеет ли user доступ к ресурсу, на который ведёт ссылка уведомления.

    Нужно, чтобы не отправить юзеру уведомление со ссылкой на чужой ресурс:
    клик дал бы 403, но сам факт видимости карточки уведомления — утечка
    (юзер узнаёт о существовании заявки/чата, к которым отношения не имеет).
    """
    user = await db.get(User, user_id)
    if user is None or not getattr(user, "is_active", True):
        return False
    try:
        role = UserRole(getattr(user, "role"))
    except ValueError:
        return False

    if link_type == "chat":
        chat = await db.get(AddressChat, link_id)
        if chat is None:
            return False
        if chat.client_user_id == user_id:
            return True
        address = await db.get(Address, chat.address_id)
        if address is None:
            return False
        return (
            role == UserRole.OWNER
            and getattr(user, "provider_id", None) == address.provider_id
        )

    if link_type == "application":
        application = await db.get(Application, link_id)
        if application is None:
            return False
        if role in _STAFF_ROLES:
            return True
        if role == UserRole.CLIENT:
            return getattr(application, "created_by", None) == user_id
        if role == UserRole.OWNER:
            return (
                getattr(user, "provider_id", None) is not None
                and getattr(application, "provider_id", None)
                == getattr(user, "provider_id", None)
            )
        return False

    # Неизвестный link_type — не пропускаем (defensive default).
    return False


async def write_user_notification(
    db: AsyncSession,
    *,
    user_id: UUID,
    kind: str,
    title: str,
    body: str,
    link_type: str | None = None,
    link_id: UUID | None = None,
) -> UserNotification:
    """Создаёт in-app уведомление.

    Если переданы link_type+link_id — ПРОВЕРЯЕМ, что user_id реально имеет
    доступ к этому ресурсу. Иначе ссылку отбрасываем (уведомление всё равно
    доставляется, но без ведущей в чужой ресурс ссылки). Так уведомление не
    превращается в канал разведки чужих заявок/чатов.
    """
    if link_type is not None and link_id is not None:
        if not await _user_can_access_link(
            db, user_id=user_id, link_type=link_type, link_id=link_id
        ):
            link_type = None
            link_id = None

    record = UserNotification(
        user_id=user_id,
        kind=kind,
        title=title,
        body=body,
        link_type=link_type,
        link_id=link_id,
    )
    db.add(record)
    await db.flush()
    return record


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

    # 1) События по заявкам.
    application_rows = await db.execute(
        _base_notification_statement(user, unread_only=unread_only)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(bounded_limit)
    )
    notifications: list[NotificationRead] = []
    for event, application in application_rows.all():
        if notification_visible_to_user(event=event, application=application, user=user):
            notifications.append(notification_read_from_row(event=event, application=application))

    # 2) Generic уведомления (чат и пр.).
    user_id = getattr(user, "id", None)
    if user_id is not None:
        stmt = select(UserNotification).where(UserNotification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(UserNotification.read_at.is_(None))
        stmt = stmt.order_by(UserNotification.created_at.desc()).limit(bounded_limit)
        for record in (await db.execute(stmt)).scalars().all():
            notifications.append(notification_read_from_user_row(record))

    # 3) Объединить и отсортировать.
    notifications.sort(key=lambda n: n.created_at, reverse=True)
    return notifications[:bounded_limit]


async def count_unread_notifications(*, db: AsyncSession, user: object) -> int:
    rows_statement = _base_notification_statement(user, unread_only=True).subquery()
    app_count = int((await db.execute(select(func.count()).select_from(rows_statement))).scalar_one())

    user_id = getattr(user, "id", None)
    user_count = 0
    if user_id is not None:
        user_count = int(
            (
                await db.execute(
                    select(func.count(UserNotification.id)).where(
                        UserNotification.user_id == user_id,
                        UserNotification.read_at.is_(None),
                    )
                )
            ).scalar_one()
        )
    return app_count + user_count


async def mark_notification_read(
    *,
    db: AsyncSession,
    event_id: UUID,
    user: object,
    source: str = "application_event",
) -> NotificationRead:
    """Помечает прочитанным. source выбирает таблицу."""
    if source == "user_notification":
        record = (
            await db.execute(
                select(UserNotification).where(
                    UserNotification.id == event_id,
                    UserNotification.user_id == getattr(user, "id"),
                )
            )
        ).scalar_one_or_none()
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Уведомление не найдено")
        if record.read_at is None:
            record.read_at = utcnow()
            await db.flush()
        return notification_read_from_user_row(record)

    # source == "application_event"
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
