from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.enums import ApplicationEventKind, ApplicationStatus, NotificationAudience, UserRole
from app.services import notification_events


def make_event(*, audience: NotificationAudience, application_id: UUID):
    return SimpleNamespace(
        id=uuid4(),
        application_id=application_id,
        kind=ApplicationEventKind.STATUS_CHANGED.value,
        audience=audience.value,
        title="Статус изменён",
        message="Заявка перешла на следующий этап.",
        payload={"status": ApplicationStatus.ASSIGNED_TO_OWNER.value},
        is_read=False,
        created_by=uuid4(),
        created_at=datetime.now(timezone.utc),
        read_at=None,
    )


def make_application(*, application_id: UUID, created_by: UUID, provider_id: UUID):
    return SimpleNamespace(
        id=application_id,
        status=ApplicationStatus.ASSIGNED_TO_OWNER.value,
        company_name="Альфа Ритейл",
        planned_client_name=None,
        created_by=created_by,
        provider_id=provider_id,
    )


def test_notification_audience_for_user_maps_staff_to_admin_audience() -> None:
    assert notification_events.notification_audience_for_user(SimpleNamespace(role=UserRole.ADMIN.value)) == NotificationAudience.ADMIN
    assert notification_events.notification_audience_for_user(SimpleNamespace(role=UserRole.MANAGER.value)) == NotificationAudience.ADMIN
    assert notification_events.notification_audience_for_user(SimpleNamespace(role=UserRole.LAWYER.value)) == NotificationAudience.ADMIN
    assert notification_events.notification_audience_for_user(SimpleNamespace(role=UserRole.CLIENT.value)) == NotificationAudience.CLIENT
    assert notification_events.notification_audience_for_user(SimpleNamespace(role=UserRole.OWNER.value)) == NotificationAudience.OWNER


def test_notification_visibility_scopes_events_to_current_user() -> None:
    application_id = uuid4()
    client_id = uuid4()
    other_client_id = uuid4()
    provider_id = uuid4()
    other_provider_id = uuid4()
    application = make_application(application_id=application_id, created_by=client_id, provider_id=provider_id)

    client_event = make_event(audience=NotificationAudience.CLIENT, application_id=application_id)
    owner_event = make_event(audience=NotificationAudience.OWNER, application_id=application_id)
    admin_event = make_event(audience=NotificationAudience.ADMIN, application_id=application_id)

    assert notification_events.notification_visible_to_user(
        event=client_event,
        application=application,
        user=SimpleNamespace(id=client_id, role=UserRole.CLIENT.value, provider_id=None),
    )
    assert not notification_events.notification_visible_to_user(
        event=client_event,
        application=application,
        user=SimpleNamespace(id=other_client_id, role=UserRole.CLIENT.value, provider_id=None),
    )
    assert notification_events.notification_visible_to_user(
        event=owner_event,
        application=application,
        user=SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id),
    )
    assert not notification_events.notification_visible_to_user(
        event=owner_event,
        application=application,
        user=SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=other_provider_id),
    )
    assert notification_events.notification_visible_to_user(
        event=admin_event,
        application=application,
        user=SimpleNamespace(id=uuid4(), role=UserRole.MANAGER.value, provider_id=None),
    )


def test_notification_read_from_row_includes_application_context() -> None:
    application_id = uuid4()
    application = make_application(application_id=application_id, created_by=uuid4(), provider_id=uuid4())
    event = make_event(audience=NotificationAudience.CLIENT, application_id=application_id)

    notification = notification_events.notification_read_from_row(event=event, application=application)

    assert notification.id == event.id
    assert notification.application_id == application_id
    assert notification.application_title == "Альфа Ритейл"
    assert notification.application_status == ApplicationStatus.ASSIGNED_TO_OWNER
    assert notification.is_read is False


@pytest.mark.asyncio
async def test_notifications_router_lists_inbox_and_marks_read(monkeypatch) -> None:
    from app.routers import notifications
    from app.schemas.notification import NotificationInboxRead

    user = SimpleNamespace(id=uuid4(), role=UserRole.CLIENT.value, provider_id=None)
    event = make_event(audience=NotificationAudience.CLIENT, application_id=uuid4())
    application = make_application(application_id=event.application_id, created_by=user.id, provider_id=uuid4())
    notification = notification_events.notification_read_from_row(event=event, application=application)

    class FakeSession:
        def __init__(self) -> None:
            self.committed = False

        async def commit(self) -> None:
            self.committed = True

    fake_db = FakeSession()

    async def fake_list_user_notifications(*, db, user, limit: int, unread_only: bool):
        assert db is fake_db
        assert limit == 20
        assert unread_only is False
        return [notification]

    async def fake_count_unread_notifications(*, db, user):
        assert db is fake_db
        return 1

    async def fake_mark_notification_read(*, db, event_id, user, source="application_event"):
        assert db is fake_db
        assert event_id == notification.id
        assert source == "application_event"
        return notification.model_copy(update={"is_read": True})

    monkeypatch.setattr(notifications, "list_user_notifications", fake_list_user_notifications)
    monkeypatch.setattr(notifications, "count_unread_notifications", fake_count_unread_notifications)
    monkeypatch.setattr(notifications, "mark_notification_read", fake_mark_notification_read)

    inbox = await notifications.get_notification_inbox(db=fake_db, user=user)
    marked = await notifications.mark_notification_as_read(event_id=notification.id, db=fake_db, user=user)

    assert isinstance(inbox, NotificationInboxRead)
    assert inbox.unread_count == 1
    assert inbox.items == [notification]
    assert marked.is_read is True
    assert fake_db.committed is True
