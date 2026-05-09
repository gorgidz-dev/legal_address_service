from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth import require_owner
from app.enums import (
    AddressPublicationStatus,
    ApplicationStatus,
    ApplicationType,
    NotificationAudience,
    UserRole,
)
from app.routers.owner_dashboard import get_owner_dashboard


@pytest.mark.asyncio
async def test_require_owner_allows_only_owner_role() -> None:
    owner = type("UserStub", (), {"role": UserRole.OWNER.value})()
    assert await require_owner(owner) is owner

    for role in (UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.LAWYER.value, UserRole.CLIENT.value):
        user = type("UserStub", (), {"role": role})()
        with pytest.raises(HTTPException) as exc:
            await require_owner(user)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_dashboard_requires_provider_binding() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_owner_dashboard(db=object(), user=SimpleNamespace(role=UserRole.OWNER.value, provider_id=None))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_owner_dashboard_includes_only_bound_provider_data_and_owner_events() -> None:
    provider_id = uuid4()
    other_provider_id = uuid4()
    address_id = uuid4()
    other_address_id = uuid4()
    application_id = uuid4()
    other_application_id = uuid4()
    now = datetime.now(timezone.utc)

    provider = SimpleNamespace(
        id=provider_id,
        code="owner-msk",
        full_name="Индивидуальный предприниматель Иванов Иван Иванович",
        short_name="ИП Иванов И. И.",
        inn=None,
        kpp=None,
        ogrn=None,
        okpo=None,
        legal_address=None,
        signatory_name=None,
        signatory_position=None,
        signatory_basis=None,
        signatory_initials=None,
        bank_name=None,
        settlement_account=None,
        corr_account=None,
        bik=None,
        phone="+7 495 000-00-00",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 1, помещение 5",
        room_number="помещение 5",
        cadastral_number="77:01:0001001:1234",
        ownership_doc="Выписка ЕГРН от 01.05.2026",
        ownership_doc_short="ЕГРН 01.05.2026",
        ownership_doc_pages=8,
        price_6m=Decimal("15000.00"),
        price_11m=Decimal("25000.00"),
        correspondence_price=Decimal("3000.00"),
        fns_number=46,
        fns_city="Москве",
        notes=None,
        is_available=True,
        publication_status=AddressPublicationStatus.PUBLISHED.value,
        created_at=now,
        updated_at=now,
    )
    hidden_address = SimpleNamespace(**{**address.__dict__, "id": other_address_id, "provider_id": other_provider_id})
    application = SimpleNamespace(
        id=application_id,
        type=ApplicationType.INITIAL_REGISTRATION.value,
        status=ApplicationStatus.ASSIGNED_TO_OWNER.value,
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
        created_by=uuid4(),
        created_at=now,
        updated_at=now,
    )
    hidden_application = SimpleNamespace(
        **{**application.__dict__, "id": other_application_id, "provider_id": other_provider_id}
    )
    hidden_admin_review = SimpleNamespace(
        **{**application.__dict__, "id": uuid4(), "status": ApplicationStatus.ADMIN_REVIEW.value}
    )
    owner_event = SimpleNamespace(
        id=uuid4(),
        application_id=application_id,
        kind="status_changed",
        audience=NotificationAudience.OWNER.value,
        title="Заявка передана исполнителю",
        message="Администратор назначил заявку на ваш адрес.",
        payload={"status": ApplicationStatus.ASSIGNED_TO_OWNER.value},
        is_read=False,
        created_by=None,
        created_at=now,
        read_at=None,
    )
    client_event = SimpleNamespace(
        **{**owner_event.__dict__, "id": uuid4(), "audience": NotificationAudience.CLIENT.value}
    )

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

        async def get(self, model, object_id):
            if model.__name__ == "Provider" and object_id == provider_id:
                return provider
            return None

        async def execute(self, _statement):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(scalars=[address, hidden_address])
            if self.calls == 2:
                return FakeResult(rows=[(application, address), (hidden_application, hidden_address), (hidden_admin_review, address)])
            return FakeResult(scalars=[owner_event, client_event])

    dashboard = await get_owner_dashboard(
        db=FakeSession(),
        user=SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id),
    )

    assert dashboard.provider.id == provider_id
    assert [item.id for item in dashboard.addresses] == [address_id]
    assert len(dashboard.applications) == 1
    owner_application = dashboard.applications[0]
    assert owner_application.id == application_id
    assert owner_application.full_address == "г. Москва, ул. Тверская, д. 1, помещение 5"
    assert owner_application.available_actions == ["accept", "reject"]
    assert [event.title for event in owner_application.events] == ["Заявка передана исполнителю"]
