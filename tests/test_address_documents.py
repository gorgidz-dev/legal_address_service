"""Документы адреса: права доступа, валидация и классификация срока."""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import AddressDocumentKind, UserRole
from app.services.address_documents import (
    EXPIRING_SOON_DAYS,
    add_address_document,
    expiry_state,
    load_owner_address,
)

TODAY = date(2026, 7, 30)
PROVIDER = uuid4()
OTHER_PROVIDER = uuid4()


def _owner(provider_id=PROVIDER):
    return SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)


def _address(provider_id=PROVIDER):
    return SimpleNamespace(id=uuid4(), provider_id=provider_id)


class _FakeDB:
    def __init__(self, address=None) -> None:
        self._address = address
        self.added: list = []

    async def get(self, _model, _id):
        return self._address

    def add(self, item) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None


def _load(db, user):
    return asyncio.run(load_owner_address(db=db, address_id=uuid4(), user=user))


# --- права ---


def test_owner_gets_own_address():
    address = _address()
    assert _load(_FakeDB(address), _owner()) is address


def test_foreign_address_is_forbidden():
    """Чужой адрес — 403, а не пустой список: молчаливая выдача скрывает ошибку прав."""
    with pytest.raises(HTTPException) as exc:
        _load(_FakeDB(_address(OTHER_PROVIDER)), _owner())
    assert exc.value.status_code == 403


def test_client_cannot_reach_address_documents():
    user = SimpleNamespace(id=uuid4(), role=UserRole.CLIENT.value, provider_id=None)
    with pytest.raises(HTTPException) as exc:
        _load(_FakeDB(_address()), user)
    assert exc.value.status_code == 403


def test_owner_without_organisation_gets_conflict():
    with pytest.raises(HTTPException) as exc:
        _load(_FakeDB(_address()), _owner(provider_id=None))
    assert exc.value.status_code == 409


def test_missing_address_is_404():
    with pytest.raises(HTTPException) as exc:
        _load(_FakeDB(None), _owner())
    assert exc.value.status_code == 404


# --- классификация срока ---


def test_document_without_expiry_is_not_a_problem():
    """У свидетельства о собственности срока нет — это не «просрочен»."""
    assert expiry_state(None, today=TODAY) == "none"


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (-1, "expired"),
        (0, "soon"),
        (EXPIRING_SOON_DAYS, "soon"),
        (EXPIRING_SOON_DAYS + 1, "valid"),
    ],
)
def test_expiry_state_boundaries(days, expected):
    assert expiry_state(date.fromordinal(TODAY.toordinal() + days), today=TODAY) == expected


# --- загрузка ---


def _add(**kwargs):
    defaults = dict(
        db=_FakeDB(),
        address=_address(),
        kind=AddressDocumentKind.OWNERSHIP_CERTIFICATE,
        title="Свидетельство",
        content=b"pdf",
        original_filename="doc.pdf",
        content_type="application/pdf",
        issued_on=None,
        expires_at=None,
        notes=None,
        user=_owner(),
    )
    defaults.update(kwargs)
    return asyncio.run(add_address_document(**defaults))


def test_empty_file_rejected():
    with pytest.raises(HTTPException) as exc:
        _add(content=b"")
    assert exc.value.status_code == 422


def test_expiry_before_issue_date_rejected():
    """Срок раньше выдачи — почти всегда опечатка в форме."""
    with pytest.raises(HTTPException) as exc:
        _add(issued_on=date(2026, 5, 1), expires_at=date(2026, 4, 1))
    assert exc.value.status_code == 422
