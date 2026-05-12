from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.enums import ApplicationStatus, ApplicationType, NoticePeriod
from app.routers import applications
from app.schemas.application import ApplicationRead, PromoteToContractRequest


def test_application_read_exposes_company_and_contact_columns() -> None:
    application = SimpleNamespace(
        id=uuid4(),
        type=ApplicationType.INITIAL_REGISTRATION,
        status=ApplicationStatus.DRAFT,
        provider_id=uuid4(),
        address_id=uuid4(),
        client_id=None,
        planned_client_name="Альфа",
        company_name="Альфа",
        contact_name="Мария Смирнова",
        contact_phone="+7 916 555-24-18",
        contact_email="maria@example.ru",
        term_months=None,
        notice_period=None,
        has_correspondence_service=False,
        contract_city=None,
        fns_number=46,
        fns_city="Москве",
        expires_at=None,
        parent_application_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = ApplicationRead.model_validate(application)

    assert payload.company_name == "Альфа"
    assert payload.contact_name == "Мария Смирнова"
    assert payload.contact_phone == "+7 916 555-24-18"
    assert payload.contact_email == "maria@example.ru"


def test_promote_to_contract_accepts_contact_updates() -> None:
    payload = PromoteToContractRequest(
        client_inn="7704217370",
        term_months=11,
        notice_period=NoticePeriod.ONE_MONTH,
        contact_name="Ирина Ковалёва",
        contact_phone="+7 925 747-11-03",
        contact_email="office@example.ru",
    )

    assert payload.contact_name == "Ирина Ковалёва"
    assert payload.contact_phone == "+79257471103"  # normalised to E.164
    assert payload.contact_email == "office@example.ru"


def test_application_read_helper_exposes_admin_workflow_actions() -> None:
    application = SimpleNamespace(
        id=uuid4(),
        type=ApplicationType.ADDRESS_CHANGE.value,
        status=ApplicationStatus.ADMIN_REVIEW.value,
        provider_id=uuid4(),
        address_id=uuid4(),
        client_id=uuid4(),
        planned_client_name=None,
        company_name="Дельта Кабинет",
        contact_name="Антон Левин",
        contact_phone="+7 495 200-14-91",
        contact_email="office@example.ru",
        term_months=11,
        notice_period=NoticePeriod.ONE_MONTH.value,
        has_correspondence_service=True,
        contract_city="Москва",
        fns_number=46,
        fns_city="Москве",
        expires_at=None,
        parent_application_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = applications.application_read(application)

    assert payload.available_actions == ["assign_owner", "request_client_fix", "cancel"]
