"""Отзывы об адресах: создание, verified-purchase гейт, модерация.

Роут-функции вызываются напрямую — HTTP-слой за auth-middleware с реальной БД.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import ApplicationStatus, ReviewStatus, UserRole
from app.models.address import Address
from app.models.application import Application
from app.models.user import User
from app.routers.address_reviews import (
    _mask_author_name,
    create_review,
    moderate_review,
)
from app.schemas.marketplace import AddressReviewCreate, ReviewModerationAction


# ----------------------------- helpers -----------------------------

class _ExecResult:
    """Имитирует результат db.execute: .scalars().first()."""

    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


class _FakeSession:
    """get_map — для db.get; exec_results — очередь ответов на db.execute."""

    def __init__(self, get_map=None, exec_results=None):
        self._get_map = get_map or {}
        self._exec = list(exec_results or [])
        self.added = []
        self.committed = False

    async def get(self, model, pk):
        return self._get_map.get((model, pk))

    async def execute(self, _stmt):
        return self._exec.pop(0) if self._exec else _ExecResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


def _client(uid=None):
    return SimpleNamespace(
        id=uid or uuid4(),
        role=UserRole.CLIENT.value,
        full_name="Алексей Морозов",
        email="client@example.com",
    )


def _address(aid=None, provider_id=None):
    return SimpleNamespace(
        id=aid or uuid4(),
        provider_id=provider_id or uuid4(),
        full_address="г. Москва, ул. Тверская, д. 7",
    )


def _completed_application(*, address_id, created_by):
    return SimpleNamespace(
        id=uuid4(),
        address_id=address_id,
        created_by=created_by,
        status=ApplicationStatus.COMPLETED.value,
    )


# ----------------------------- _mask_author_name -----------------------------

def test_mask_author_name():
    assert _mask_author_name("Алексей Морозов") == "Алексей М."
    assert _mask_author_name("Иван") == "Иван"
    assert _mask_author_name("") == "Клиент"
    assert _mask_author_name("  ") == "Клиент"


# ----------------------------- create_review -----------------------------

@pytest.mark.asyncio
async def test_create_review_ok_with_completed_application():
    user = _client()
    address = _address()
    app_row = _completed_application(address_id=address.id, created_by=user.id)
    db = _FakeSession(
        get_map={(Address, address.id): address},
        exec_results=[_ExecResult([app_row]), _ExecResult([])],  # app found, no existing review
    )
    payload = AddressReviewCreate(rating=5, body="Отличный адрес, всё чётко прошло.")
    result = await create_review(address.id, payload, db=db, user=user)
    assert result.rating == 5
    assert result.author_name == "Алексей М."
    assert db.committed is True
    assert db.added and db.added[0].status == ReviewStatus.PENDING.value


@pytest.mark.asyncio
async def test_create_review_blocked_without_completed_application():
    user = _client()
    address = _address()
    db = _FakeSession(
        get_map={(Address, address.id): address},
        exec_results=[_ExecResult([])],  # нет завершённой заявки
    )
    payload = AddressReviewCreate(rating=4, body="Хочу оставить отзыв без заявки.")
    with pytest.raises(HTTPException) as exc:
        await create_review(address.id, payload, db=db, user=user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_review_non_client_forbidden():
    owner = SimpleNamespace(
        id=uuid4(), role=UserRole.OWNER.value, full_name="O O", email="o@e.com"
    )
    address = _address()
    db = _FakeSession(get_map={(Address, address.id): address})
    payload = AddressReviewCreate(rating=5, body="Текст достаточной длины тут.")
    with pytest.raises(HTTPException) as exc:
        await create_review(address.id, payload, db=db, user=owner)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_review_duplicate_conflict():
    user = _client()
    address = _address()
    app_row = _completed_application(address_id=address.id, created_by=user.id)
    existing = SimpleNamespace(id=uuid4())
    db = _FakeSession(
        get_map={(Address, address.id): address},
        exec_results=[_ExecResult([app_row]), _ExecResult([existing])],
    )
    payload = AddressReviewCreate(rating=3, body="Повторный отзыв на тот же адрес.")
    with pytest.raises(HTTPException) as exc:
        await create_review(address.id, payload, db=db, user=user)
    assert exc.value.status_code == 409


# ----------------------------- moderate_review -----------------------------

def _pending_review(address_id=None):
    return SimpleNamespace(
        id=uuid4(),
        address_id=address_id or uuid4(),
        client_user_id=uuid4(),
        rating=5,
        body="Текст отзыва длиной достаточной.",
        status=ReviewStatus.PENDING.value,
        moderation_note=None,
        moderated_at=None,
        moderated_by=None,
        owner_reply=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_moderate_review_publish():
    from app.models.address_review import AddressReview

    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value)
    review = _pending_review()
    address = _address(aid=review.address_id)
    author = _client(uid=review.client_user_id)
    db = _FakeSession(
        get_map={
            (AddressReview, review.id): review,
            (Address, review.address_id): address,
            (User, review.client_user_id): author,
        }
    )
    result = await moderate_review(
        review.id, ReviewModerationAction(action="publish"), db=db, admin=admin
    )
    assert result.status == ReviewStatus.PUBLISHED.value
    assert review.moderated_by == admin.id
    assert db.committed is True


@pytest.mark.asyncio
async def test_moderate_review_reject_with_note():
    from app.models.address_review import AddressReview

    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value)
    review = _pending_review()
    address = _address(aid=review.address_id)
    author = _client(uid=review.client_user_id)
    db = _FakeSession(
        get_map={
            (AddressReview, review.id): review,
            (Address, review.address_id): address,
            (User, review.client_user_id): author,
        }
    )
    result = await moderate_review(
        review.id,
        ReviewModerationAction(action="reject", note="Спам / реклама"),
        db=db,
        admin=admin,
    )
    assert result.status == ReviewStatus.REJECTED.value
    assert result.moderation_note == "Спам / реклама"


@pytest.mark.asyncio
async def test_moderate_review_already_moderated_conflict():
    from app.models.address_review import AddressReview

    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value)
    review = _pending_review()
    review.status = ReviewStatus.PUBLISHED.value  # уже промодерирован
    db = _FakeSession(get_map={(AddressReview, review.id): review})
    with pytest.raises(HTTPException) as exc:
        await moderate_review(
            review.id, ReviewModerationAction(action="reject"), db=db, admin=admin
        )
    assert exc.value.status_code == 409
