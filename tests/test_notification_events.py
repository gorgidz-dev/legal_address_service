from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.enums import ApplicationEventKind, NotificationAudience
from app.services.notification_events import event_values, event_visible_to_role


def test_event_values_builds_consistent_payload() -> None:
    application_id = uuid4()
    created_by = uuid4()

    values = event_values(
        application_id=application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.CLIENT,
        title="Статус изменен",
        message="Заявка перешла на проверку",
        payload={"status": "admin_review"},
        created_by=created_by,
    )

    assert values["application_id"] == application_id
    assert values["kind"] == "status_changed"
    assert values["audience"] == "client"
    assert values["payload"] == {"status": "admin_review"}
    assert values["created_by"] == created_by


def test_event_visibility_matches_audience_and_admin_roles() -> None:
    client_event = SimpleNamespace(audience="client")
    owner_event = SimpleNamespace(audience="owner")
    admin_event = SimpleNamespace(audience="admin")

    assert event_visible_to_role(client_event, "client")
    assert not event_visible_to_role(client_event, "owner")
    assert event_visible_to_role(owner_event, "owner")
    assert event_visible_to_role(admin_event, "admin")
    assert event_visible_to_role(admin_event, "manager")
    assert event_visible_to_role(admin_event, "lawyer")
