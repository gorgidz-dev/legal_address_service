from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, ApplicationType, NotificationAudience, UserRole
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.schemas.workflow import ApplicationActionResult
from app.services.application_workflow import apply_application_action


def make_application(
    *,
    status: ApplicationStatus,
    provider_id: UUID | None = None,
    created_by: UUID | None = None,
) -> Application:
    now = datetime.now(timezone.utc)
    return Application(
        id=uuid4(),
        type=ApplicationType.INITIAL_REGISTRATION.value,
        provider_id=provider_id or uuid4(),
        address_id=uuid4(),
        planned_client_name="Вектор Право",
        company_name="Вектор Право",
        contact_name="Ирина Ковалёва",
        contact_phone="+7 925 747-11-03",
        contact_email="client@example.ru",
        has_correspondence_service=False,
        status=status.value,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


class FakeWorkflowSession:
    def __init__(self, application: Application):
        self.application = application
        self.added: list[object] = []
        self.flushed = False

    async def get(self, model, object_id):
        if model.__name__ == "Application" and object_id == self.application.id:
            return self.application
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed = True
        now = datetime.now(timezone.utc)
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "created_at", None) is None:
                item.created_at = now


@pytest.mark.asyncio
async def test_staff_assign_owner_moves_admin_review_to_owner_queue() -> None:
    application = make_application(status=ApplicationStatus.ADMIN_REVIEW, created_by=uuid4())
    db = FakeWorkflowSession(application)
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value, provider_id=None)

    result = await apply_application_action(
        db=db,
        application_id=application.id,
        action="assign_owner",
        user=admin,
    )

    assert isinstance(result, ApplicationActionResult)
    assert application.status == ApplicationStatus.ASSIGNED_TO_OWNER.value
    assert result.status == ApplicationStatus.ASSIGNED_TO_OWNER
    assert result.available_actions == ["accept", "reject"]
    assert db.flushed

    events = [item for item in db.added if isinstance(item, ApplicationEvent)]
    assert {event.audience for event in events} == {
        NotificationAudience.ADMIN.value,
        NotificationAudience.CLIENT.value,
        NotificationAudience.OWNER.value,
    }
    owner_event = next(event for event in events if event.audience == NotificationAudience.OWNER.value)
    assert owner_event.title == "Заявка передана исполнителю"
    assert owner_event.payload == {
        "action": "assign_owner",
        "previous_status": ApplicationStatus.ADMIN_REVIEW.value,
        "status": ApplicationStatus.ASSIGNED_TO_OWNER.value,
    }


@pytest.mark.asyncio
async def test_owner_accepts_only_own_provider_application() -> None:
    provider_id = uuid4()
    application = make_application(status=ApplicationStatus.ASSIGNED_TO_OWNER, provider_id=provider_id)
    db = FakeWorkflowSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)

    result = await apply_application_action(
        db=db,
        application_id=application.id,
        action="accept",
        user=owner,
    )

    assert application.status == ApplicationStatus.ACCEPTED_BY_OWNER.value
    assert result.available_actions == ["start_documents"]
    assert any(
        event.audience == NotificationAudience.ADMIN.value and event.payload["action"] == "accept"
        for event in db.added
        if isinstance(event, ApplicationEvent)
    )


@pytest.mark.asyncio
async def test_staff_reassigns_rejected_owner_application() -> None:
    application = make_application(status=ApplicationStatus.REJECTED_BY_OWNER, created_by=uuid4())
    db = FakeWorkflowSession(application)
    admin = SimpleNamespace(id=uuid4(), role=UserRole.MANAGER.value, provider_id=None)

    result = await apply_application_action(
        db=db,
        application_id=application.id,
        action="assign_owner",
        user=admin,
    )

    assert application.status == ApplicationStatus.ASSIGNED_TO_OWNER.value
    assert result.available_actions == ["accept", "reject"]
    assert any(
        event.audience == NotificationAudience.OWNER.value and event.payload["action"] == "assign_owner"
        for event in db.added
        if isinstance(event, ApplicationEvent)
    )


@pytest.mark.asyncio
async def test_owner_cannot_change_another_provider_application() -> None:
    application = make_application(status=ApplicationStatus.ASSIGNED_TO_OWNER, provider_id=uuid4())
    db = FakeWorkflowSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=uuid4())

    with pytest.raises(HTTPException) as exc:
        await apply_application_action(
            db=db,
            application_id=application.id,
            action="accept",
            user=owner,
        )

    assert exc.value.status_code == 403
    assert application.status == ApplicationStatus.ASSIGNED_TO_OWNER.value
    assert db.added == []


@pytest.mark.asyncio
async def test_invalid_transition_is_rejected_without_mutation() -> None:
    provider_id = uuid4()
    application = make_application(status=ApplicationStatus.ADMIN_REVIEW, provider_id=provider_id)
    db = FakeWorkflowSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)

    with pytest.raises(HTTPException) as exc:
        await apply_application_action(
            db=db,
            application_id=application.id,
            action="accept",
            user=owner,
        )

    assert exc.value.status_code == 409
    assert "Недоступное действие" in exc.value.detail
    assert application.status == ApplicationStatus.ADMIN_REVIEW.value
    assert db.added == []


@pytest.mark.asyncio
async def test_client_confirms_ready_application_as_completed() -> None:
    user_id = uuid4()
    application = make_application(status=ApplicationStatus.READY_FOR_CLIENT, created_by=user_id)
    db = FakeWorkflowSession(application)
    client = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, provider_id=None)

    result = await apply_application_action(
        db=db,
        application_id=application.id,
        action="confirm_received",
        user=client,
    )

    assert application.status == ApplicationStatus.COMPLETED.value
    assert result.available_actions == []
    assert any(
        event.audience == NotificationAudience.ADMIN.value and event.payload["action"] == "confirm_received"
        for event in db.added
        if isinstance(event, ApplicationEvent)
    )
