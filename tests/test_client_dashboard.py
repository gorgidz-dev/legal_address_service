from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import require_client
from app.enums import ApplicationStatus, ApplicationType, NotificationAudience, UserRole
from app.routers.client_dashboard import list_client_applications


@pytest.mark.asyncio
async def test_require_client_allows_only_client_role() -> None:
    client = type("UserStub", (), {"role": UserRole.CLIENT.value})()
    assert await require_client(client) is client

    for role in (UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.LAWYER.value, UserRole.OWNER.value):
        user = type("UserStub", (), {"role": role})()
        with pytest.raises(HTTPException) as exc:
            await require_client(user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_applications_include_only_owned_applications_with_public_timeline() -> None:
    client_user_id = uuid4()
    other_user_id = uuid4()
    provider_id = uuid4()
    address_id = uuid4()
    visible_application_id = uuid4()
    hidden_application_id = uuid4()
    now = datetime.now(timezone.utc)

    visible_application = SimpleNamespace(
        id=visible_application_id,
        type=ApplicationType.INITIAL_REGISTRATION.value,
        status=ApplicationStatus.ADMIN_REVIEW.value,
        provider_id=provider_id,
        address_id=address_id,
        client_id=None,
        planned_client_name="Альфа",
        company_name="Альфа",
        contact_name="Иван Клиентов",
        contact_phone="+7 900 000-00-00",
        contact_email="client@example.com",
        term_months=11,
        notice_period=None,
        has_correspondence_service=False,
        contract_city="Москва",
        fns_number=46,
        fns_city="Москве",
        expires_at=None,
        parent_application_id=None,
        created_by=client_user_id,
        created_at=now,
        updated_at=now,
    )
    hidden_application = SimpleNamespace(
        **{
            **visible_application.__dict__,
            "id": hidden_application_id,
            "created_by": other_user_id,
            "contact_email": "other@example.com",
        }
    )
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 1, помещение 5",
        room_number="помещение 5",
        price_6m=Decimal("15000.00"),
        price_11m=Decimal("25000.00"),
        correspondence_price=Decimal("3000.00"),
    )
    provider = SimpleNamespace(id=provider_id, short_name="Адресный актив")
    client_event = SimpleNamespace(
        id=uuid4(),
        application_id=visible_application_id,
        kind="created",
        audience=NotificationAudience.CLIENT.value,
        title="Заявка создана",
        message="Заявка отправлена администратору на ручную проверку.",
        payload={"status": ApplicationStatus.ADMIN_REVIEW.value},
        is_read=False,
        created_by=client_user_id,
        created_at=now,
        read_at=None,
    )
    admin_event = SimpleNamespace(
        **{
            **client_event.__dict__,
            "id": uuid4(),
            "audience": NotificationAudience.ADMIN.value,
            "title": "Внутренняя заметка",
        }
    )

    class FakeRows:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeResult:
        def __init__(self, rows=None, scalars=None):
            self._rows = rows or []
            self._scalars = scalars or []

        def all(self):
            return self._rows

        def scalars(self):
            return FakeScalars(self._scalars)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(
                    rows=[
                        (visible_application, address, provider),
                        (hidden_application, address, provider),
                    ]
                )
            return FakeResult(scalars=[client_event, admin_event])

    result = await list_client_applications(
        db=FakeSession(),
        user=SimpleNamespace(id=client_user_id, role=UserRole.CLIENT.value),
    )

    assert len(result) == 1
    application = result[0]
    assert application.id == visible_application_id
    assert application.provider_name == "Адресный актив"
    assert application.full_address == "г. Москва, ул. Тверская, д. 1, помещение 5"
    assert application.selected_price == Decimal("25000.00")
    assert [event.title for event in application.events] == ["Заявка создана"]
