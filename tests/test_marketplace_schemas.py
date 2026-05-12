from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.enums import OwnerConnectionRequestStatus, UserRole
from app.schemas.auth import CurrentUserRead, InvitationCreate
from app.schemas.marketplace import ProviderConnectionRequestCreate, ProviderConnectionRequestRead


def test_invitation_create_accepts_owner_role() -> None:
    payload = InvitationCreate(email="owner@example.ru", full_name="Анна Собственник", role=UserRole.OWNER)

    assert payload.role == UserRole.OWNER


def test_current_user_read_exposes_provider_id() -> None:
    provider_id = uuid4()
    payload = CurrentUserRead(
        id=uuid4(),
        email="owner@example.ru",
        full_name="Анна Собственник",
        role=UserRole.OWNER,
        is_active=True,
        provider_id=provider_id,
    )

    assert payload.provider_id == provider_id


def test_provider_connection_request_create_normalizes_email() -> None:
    payload = ProviderConnectionRequestCreate(
        company_name="ООО Адресный фонд",
        contact_name="Игорь Петров",
        contact_email="Owner@Example.Ru",
        contact_phone="+7 900 000-00-00",
        city="Москва",
        address_count=4,
        comment="Есть помещения в ЦАО",
    )

    assert payload.contact_email == "owner@example.ru"  # full lowercase
    assert payload.contact_phone == "+79000000000"  # normalised to E.164
    assert payload.address_count == 4


def test_provider_connection_request_read_shape() -> None:
    payload = ProviderConnectionRequestRead(
        id=uuid4(),
        company_name="ООО Адресный фонд",
        contact_name="Игорь Петров",
        contact_email="owner@example.ru",
        contact_phone="+7 900 000-00-00",
        city="Москва",
        address_count=4,
        comment="Есть помещения в ЦАО",
        status=OwnerConnectionRequestStatus.NEW,
        admin_comment=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert payload.status == OwnerConnectionRequestStatus.NEW
