from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import AddressPublicationStatus, UserRole
from app.models.address import Address
from app.routers.address_moderation import (
    admin_list_addresses_for_moderation,
    archive_address,
    publish_address,
    reject_address,
    submit_address_for_moderation,
)
from app.schemas.address import AddressModerationReject


def _now():
    return datetime.now(timezone.utc)


def _make_address(
    *,
    status: AddressPublicationStatus = AddressPublicationStatus.DRAFT,
    provider_id=None,
):
    a = Address(
        full_address="г. Москва, ул. Тверская, д. 1",
        cadastral_number="77:01:0001001:1234",
        ownership_doc="ЕГРН выписка",
        ownership_doc_short="ЕГРН",
        price_6m=15000,
        price_11m=25000,
        provider_id=provider_id or uuid4(),
        publication_status=status.value,
        is_available=True,
    )
    a.id = uuid4()
    a.created_at = _now()
    a.updated_at = _now()
    return a


def _user(role: UserRole, provider_id=None):
    return SimpleNamespace(
        id=uuid4(),
        email=f"{role.value}@example.ru",
        role=role.value,
        is_active=True,
        provider_id=provider_id,
    )


class _FakeDB:
    def __init__(self, addresses):
        self._addresses = {a.id: a for a in addresses}
        self.committed = False

    async def get(self, model, key):
        if model is Address:
            return self._addresses.get(key)
        return None

    async def execute(self, _stmt):
        items = list(self._addresses.values())

        class _R:
            def scalars(self):
                return SimpleNamespace(all=lambda: items)

        return _R()

    async def commit(self):
        self.committed = True

    async def refresh(self, item):
        item.updated_at = _now()


@pytest.mark.asyncio
async def test_owner_submits_draft_address_to_moderation() -> None:
    provider_id = uuid4()
    addr = _make_address(status=AddressPublicationStatus.DRAFT, provider_id=provider_id)
    owner = _user(UserRole.OWNER, provider_id=provider_id)
    db = _FakeDB([addr])

    result = await submit_address_for_moderation(address_id=addr.id, db=db, user=owner)

    assert result.publication_status == AddressPublicationStatus.MODERATION.value
    assert db.committed


@pytest.mark.asyncio
async def test_owner_can_resubmit_after_rejection() -> None:
    provider_id = uuid4()
    addr = _make_address(status=AddressPublicationStatus.REJECTED, provider_id=provider_id)
    addr.moderation_comment = "Не хватает фото"
    owner = _user(UserRole.OWNER, provider_id=provider_id)
    db = _FakeDB([addr])

    result = await submit_address_for_moderation(address_id=addr.id, db=db, user=owner)

    assert result.publication_status == AddressPublicationStatus.MODERATION.value
    assert result.moderation_comment is None  # comment cleared on resubmit


@pytest.mark.asyncio
async def test_owner_cannot_submit_already_published_address() -> None:
    provider_id = uuid4()
    addr = _make_address(status=AddressPublicationStatus.PUBLISHED, provider_id=provider_id)
    owner = _user(UserRole.OWNER, provider_id=provider_id)
    db = _FakeDB([addr])

    with pytest.raises(HTTPException) as exc:
        await submit_address_for_moderation(address_id=addr.id, db=db, user=owner)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_owner_cannot_act_on_foreign_provider_address() -> None:
    addr = _make_address(status=AddressPublicationStatus.DRAFT, provider_id=uuid4())
    foreign_owner = _user(UserRole.OWNER, provider_id=uuid4())
    db = _FakeDB([addr])

    with pytest.raises(HTTPException) as exc:
        await submit_address_for_moderation(address_id=addr.id, db=db, user=foreign_owner)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_cannot_submit_address() -> None:
    addr = _make_address(status=AddressPublicationStatus.DRAFT)
    client = _user(UserRole.CLIENT)
    db = _FakeDB([addr])

    with pytest.raises(HTTPException) as exc:
        await submit_address_for_moderation(address_id=addr.id, db=db, user=client)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_publishes_moderation_address() -> None:
    addr = _make_address(status=AddressPublicationStatus.MODERATION)
    admin = _user(UserRole.ADMIN)
    db = _FakeDB([addr])

    result = await publish_address(address_id=addr.id, db=db, admin=admin)

    assert result.publication_status == AddressPublicationStatus.PUBLISHED.value
    assert result.moderated_by == admin.id
    assert result.moderated_at is not None
    assert result.published_at is not None


@pytest.mark.asyncio
async def test_admin_cannot_publish_draft_address() -> None:
    addr = _make_address(status=AddressPublicationStatus.DRAFT)
    admin = _user(UserRole.ADMIN)
    db = _FakeDB([addr])

    with pytest.raises(HTTPException) as exc:
        await publish_address(address_id=addr.id, db=db, admin=admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_admin_rejects_with_comment() -> None:
    addr = _make_address(status=AddressPublicationStatus.MODERATION)
    admin = _user(UserRole.ADMIN)
    db = _FakeDB([addr])

    result = await reject_address(
        address_id=addr.id,
        payload=AddressModerationReject(moderation_comment="Нужны фото комнаты"),
        db=db,
        admin=admin,
    )

    assert result.publication_status == AddressPublicationStatus.REJECTED.value
    assert result.moderation_comment == "Нужны фото комнаты"
    assert result.moderated_by == admin.id


@pytest.mark.asyncio
async def test_owner_archives_published_address() -> None:
    provider_id = uuid4()
    addr = _make_address(status=AddressPublicationStatus.PUBLISHED, provider_id=provider_id)
    owner = _user(UserRole.OWNER, provider_id=provider_id)
    db = _FakeDB([addr])

    result = await archive_address(address_id=addr.id, db=db, user=owner)

    assert result.publication_status == AddressPublicationStatus.ARCHIVED.value


@pytest.mark.asyncio
async def test_archive_idempotency_blocked() -> None:
    addr = _make_address(status=AddressPublicationStatus.ARCHIVED)
    admin = _user(UserRole.ADMIN)
    db = _FakeDB([addr])

    with pytest.raises(HTTPException) as exc:
        await archive_address(address_id=addr.id, db=db, user=admin)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_admin_list_filters_by_status() -> None:
    a = _make_address(status=AddressPublicationStatus.MODERATION)
    b = _make_address(status=AddressPublicationStatus.DRAFT)
    db = _FakeDB([a, b])

    result = await admin_list_addresses_for_moderation(publication_status=None, db=db)

    assert {x.id for x in result} == {a.id, b.id}
