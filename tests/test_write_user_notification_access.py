"""write_user_notification: проверка доступа к ресурсу ссылки.

Если уведомлению передан link_type/link_id, на ресурс к которому у user'а
нет доступа — ссылка должна быть отброшена (link_type/link_id → None).
Иначе карточка уведомления = канал разведки чужих чатов/заявок.

См. app/services/notification_events.py::write_user_notification.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.enums import UserRole
from app.models.address import Address
from app.models.address_chat import AddressChat
from app.models.application import Application
from app.models.user import User
from app.services.notification_events import write_user_notification


class _FakeDB:
    """db.get(Model, pk) отдаёт объект из заранее заданной карты."""

    def __init__(self, objects: dict):
        # objects: {(Model, pk): obj}
        self._objects = objects
        self.added = []

    async def get(self, model, pk):
        return self._objects.get((model, pk))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


async def _write(db, *, user_id, link_type, link_id):
    return await write_user_notification(
        db,
        user_id=user_id,
        kind="test",
        title="t",
        body="b",
        link_type=link_type,
        link_id=link_id,
    )


# ----------------------------- chat -----------------------------

@pytest.mark.asyncio
async def test_chat_link_kept_for_chat_client():
    user_id, chat_id, addr_id, prov_id = uuid4(), uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, is_active=True, provider_id=None)
    chat = SimpleNamespace(id=chat_id, address_id=addr_id, client_user_id=user_id)
    address = SimpleNamespace(id=addr_id, provider_id=prov_id)
    db = _FakeDB({(User, user_id): user, (AddressChat, chat_id): chat, (Address, addr_id): address})

    rec = await _write(db, user_id=user_id, link_type="chat", link_id=chat_id)
    assert rec.link_type == "chat"
    assert rec.link_id == chat_id


@pytest.mark.asyncio
async def test_chat_link_kept_for_owner_of_address_provider():
    user_id, chat_id, addr_id, prov_id = uuid4(), uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.OWNER.value, is_active=True, provider_id=prov_id)
    chat = SimpleNamespace(id=chat_id, address_id=addr_id, client_user_id=uuid4())
    address = SimpleNamespace(id=addr_id, provider_id=prov_id)
    db = _FakeDB({(User, user_id): user, (AddressChat, chat_id): chat, (Address, addr_id): address})

    rec = await _write(db, user_id=user_id, link_type="chat", link_id=chat_id)
    assert rec.link_type == "chat"


@pytest.mark.asyncio
async def test_chat_link_dropped_for_stranger():
    """Юзер не клиент чата и не owner провайдера — ссылку отбрасываем."""
    user_id, chat_id, addr_id = uuid4(), uuid4(), uuid4()
    user = SimpleNamespace(
        id=user_id, role=UserRole.OWNER.value, is_active=True, provider_id=uuid4()
    )
    chat = SimpleNamespace(id=chat_id, address_id=addr_id, client_user_id=uuid4())
    address = SimpleNamespace(id=addr_id, provider_id=uuid4())  # другой провайдер
    db = _FakeDB({(User, user_id): user, (AddressChat, chat_id): chat, (Address, addr_id): address})

    rec = await _write(db, user_id=user_id, link_type="chat", link_id=chat_id)
    assert rec.link_type is None
    assert rec.link_id is None


# --------------------------- application ---------------------------

@pytest.mark.asyncio
async def test_application_link_kept_for_creator_client():
    user_id, app_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, is_active=True, provider_id=None)
    application = SimpleNamespace(id=app_id, created_by=user_id, provider_id=uuid4())
    db = _FakeDB({(User, user_id): user, (Application, app_id): application})

    rec = await _write(db, user_id=user_id, link_type="application", link_id=app_id)
    assert rec.link_type == "application"


@pytest.mark.asyncio
async def test_application_link_dropped_for_foreign_client():
    user_id, app_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, is_active=True, provider_id=None)
    application = SimpleNamespace(id=app_id, created_by=uuid4(), provider_id=uuid4())
    db = _FakeDB({(User, user_id): user, (Application, app_id): application})

    rec = await _write(db, user_id=user_id, link_type="application", link_id=app_id)
    assert rec.link_type is None
    assert rec.link_id is None


@pytest.mark.asyncio
async def test_application_link_kept_for_staff():
    user_id, app_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.ADMIN.value, is_active=True, provider_id=None)
    application = SimpleNamespace(id=app_id, created_by=uuid4(), provider_id=uuid4())
    db = _FakeDB({(User, user_id): user, (Application, app_id): application})

    rec = await _write(db, user_id=user_id, link_type="application", link_id=app_id)
    assert rec.link_type == "application"


# ----------------------------- edge -----------------------------

@pytest.mark.asyncio
async def test_no_link_means_no_check():
    user_id = uuid4()
    db = _FakeDB({})  # db.get никогда не вызовется
    rec = await _write(db, user_id=user_id, link_type=None, link_id=None)
    assert rec.link_type is None


@pytest.mark.asyncio
async def test_unknown_link_type_dropped():
    user_id, some_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, is_active=True, provider_id=None)
    db = _FakeDB({(User, user_id): user})
    rec = await _write(db, user_id=user_id, link_type="secret_resource", link_id=some_id)
    assert rec.link_type is None


@pytest.mark.asyncio
async def test_link_dropped_when_resource_missing():
    """link_id указывает на несуществующий чат — ссылку отбрасываем."""
    user_id, chat_id = uuid4(), uuid4()
    user = SimpleNamespace(id=user_id, role=UserRole.CLIENT.value, is_active=True, provider_id=None)
    db = _FakeDB({(User, user_id): user})  # чата нет в карте
    rec = await _write(db, user_id=user_id, link_type="chat", link_id=chat_id)
    assert rec.link_type is None
