"""Доступ к открытию чата по адресу.

Проверяем фикс информационной разведки: клиент не должен иметь возможность
открыть чат (а значит — подтвердить существование) адреса, который не
опубликован или снят с публикации. См. open_chat_for_address в
app/routers/address_chats.py.

Вызываем функцию-роут напрямую — HTTP-слой обёрнут auth-middleware'ом,
который ходит в реальную БД, поэтому через TestClient этот эндпоинт не
протестировать без живой сессии.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import AddressPublicationStatus, UserRole
from app.routers.address_chats import open_chat_for_address


def _client_user():
    return SimpleNamespace(
        id=uuid4(), role=UserRole.CLIENT.value, email="client@example.com"
    )


def _address(*, publication_status: str, is_available: bool):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        provider_id=uuid4(),
        full_address="г. Москва, ул. Скрытая, д. 1",
        publication_status=publication_status,
        is_available=is_available,
        provider=SimpleNamespace(short_name="Тайный Провайдер"),
        created_at=now,
        updated_at=now,
    )


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """1-й execute → address, 2-й → None (существующего чата нет)."""

    def __init__(self, address, existing_chat=None):
        self._address = address
        self._existing_chat = existing_chat
        self.calls = 0
        self.committed = False

    async def execute(self, _stmt):
        self.calls += 1
        if self.calls == 1:
            return _Result(self._address)
        return _Result(self._existing_chat)

    def add(self, _obj):
        pass

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        obj.last_message_at = None


@pytest.mark.asyncio
async def test_open_chat_published_available_address_ok():
    address = _address(
        publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=True
    )
    session = _FakeSession(address)
    result = await open_chat_for_address(address.id, db=session, user=_client_user())
    assert result.provider_name == "Тайный Провайдер"
    assert session.committed is True


@pytest.mark.asyncio
async def test_open_chat_unpublished_address_is_hidden():
    """draft / moderation / archived / rejected → 404, как несуществующий."""
    for hidden in (
        AddressPublicationStatus.DRAFT.value,
        AddressPublicationStatus.MODERATION.value,
        AddressPublicationStatus.ARCHIVED.value,
        AddressPublicationStatus.REJECTED.value,
    ):
        address = _address(publication_status=hidden, is_available=True)
        session = _FakeSession(address)
        with pytest.raises(HTTPException) as exc:
            await open_chat_for_address(address.id, db=session, user=_client_user())
        assert exc.value.status_code == 404, hidden
        assert session.committed is False, hidden


@pytest.mark.asyncio
async def test_open_chat_unavailable_address_is_hidden():
    """Опубликован, но снят с продажи (is_available=False) → 404."""
    address = _address(
        publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=False
    )
    session = _FakeSession(address)
    with pytest.raises(HTTPException) as exc:
        await open_chat_for_address(address.id, db=session, user=_client_user())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_open_chat_existing_chat_survives_unpublish():
    """Если чат уже создан, а адрес позже сняли с публикации — доступ остаётся.

    Блокируем только СОЗДАНИЕ нового чата, не доступ к существующей переписке.
    """
    address = _address(
        publication_status=AddressPublicationStatus.ARCHIVED.value, is_available=False
    )
    existing = SimpleNamespace(
        id=uuid4(),
        address_id=address.id,
        client_user_id=uuid4(),
        last_message_at=None,
        created_at=datetime.now(timezone.utc),
    )
    session = _FakeSession(address, existing_chat=existing)
    result = await open_chat_for_address(address.id, db=session, user=_client_user())
    assert result.id == existing.id
    assert session.committed is False  # ничего не создавали


@pytest.mark.asyncio
async def test_open_chat_non_client_role_forbidden():
    """Открыть чат может только клиент — owner/admin получают 403."""
    address = _address(
        publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=True
    )
    owner = SimpleNamespace(
        id=uuid4(), role=UserRole.OWNER.value, email="owner@example.com"
    )
    session = _FakeSession(address)
    with pytest.raises(HTTPException) as exc:
        await open_chat_for_address(address.id, db=session, user=owner)
    assert exc.value.status_code == 403
