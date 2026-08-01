"""Правила переписки на троих.

Здесь проверяются места, где чат легко сделать неправильно и не заметить:
кого пускать, чьим именем подписано сообщение и что считать непрочитанным.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import UserRole
from app.services.chat_threads import (
    PLATFORM_SIGNATURE,
    author_side,
    display_name,
    ensure_application_access,
    ensure_participant,
    is_participant,
    is_staff,
    mark_read,
    resolve_thread_for_application,
    unread_counts,
)

PROVIDER = uuid4()
OTHER_PROVIDER = uuid4()
CLIENT_ID = uuid4()
T0 = datetime(2026, 8, 1, 9, tzinfo=timezone.utc)


def _user(role: UserRole, *, user_id=None, provider_id=None, full_name="", email="u@example.com"):
    return SimpleNamespace(
        id=user_id or uuid4(),
        role=role.value,
        provider_id=provider_id,
        full_name=full_name,
        email=email,
    )


def _chat(chat_id=None):
    return SimpleNamespace(
        id=chat_id or uuid4(), address_id=uuid4(), client_user_id=CLIENT_ID
    )


def _address(provider_id=PROVIDER):
    return SimpleNamespace(id=uuid4(), provider_id=provider_id)


# --- кто участник ---


def test_client_of_the_thread_is_participant():
    chat, address = _chat(), _address()
    assert is_participant(_user(UserRole.CLIENT, user_id=CLIENT_ID), chat, address)


def test_another_client_is_not_participant():
    chat, address = _chat(), _address()
    assert not is_participant(_user(UserRole.CLIENT), chat, address)


def test_owner_of_the_address_is_participant():
    chat, address = _chat(), _address()
    owner = _user(UserRole.OWNER, provider_id=PROVIDER)
    assert is_participant(owner, chat, address)


def test_owner_of_another_organisation_is_not():
    chat, address = _chat(), _address()
    stranger = _user(UserRole.OWNER, provider_id=OTHER_PROVIDER)
    assert not is_participant(stranger, chat, address)


def test_owner_without_organisation_is_not():
    """provider_id=None не должен совпасть с адресом без провайдера."""
    chat, address = _chat(), _address(provider_id=None)
    assert not is_participant(_user(UserRole.OWNER, provider_id=None), chat, address)


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER])
def test_all_staff_roles_are_participants(role):
    """Юрист и менеджер — та же площадка, что и админ.

    Раньше пускали только admin: юрист видел комплект документов заявки, но в
    переписке по ней получал 403.
    """
    chat, address = _chat(), _address()
    assert is_participant(_user(role), chat, address)
    assert is_staff(_user(role))


def test_ensure_participant_raises_403_for_stranger():
    chat, address = _chat(), _address()
    with pytest.raises(HTTPException) as exc:
        ensure_participant(_user(UserRole.CLIENT), chat, address)
    assert exc.value.status_code == 403


# --- чьё сообщение ---


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.CLIENT, "client"),
        (UserRole.OWNER, "owner"),
        (UserRole.ADMIN, "staff"),
        (UserRole.MANAGER, "staff"),
        (UserRole.LAWYER, "staff"),
    ],
)
def test_author_side(role, expected):
    assert author_side(_user(role)) == expected


def test_staff_name_is_hidden_from_client():
    operator = _user(UserRole.ADMIN, full_name="Иванова А.")
    name = display_name(operator, viewer=_user(UserRole.CLIENT), provider_name="ООО Ромашка")
    assert name == PLATFORM_SIGNATURE
    assert "Иванова" not in name


def test_staff_name_is_hidden_from_owner():
    operator = _user(UserRole.LAWYER, full_name="Петров П.")
    name = display_name(operator, viewer=_user(UserRole.OWNER), provider_name="ООО Ромашка")
    assert name == PLATFORM_SIGNATURE


def test_staff_sees_which_colleague_answered():
    operator = _user(UserRole.MANAGER, full_name="Иванова А.")
    name = display_name(operator, viewer=_user(UserRole.ADMIN), provider_name="")
    assert name == "Иванова А."


def test_owner_is_signed_by_organisation_not_by_person():
    """Клиенту важна организация, а личная почта собственника ему не нужна."""
    owner = _user(UserRole.OWNER, full_name="Сидоров С.", email="owner@example.com")
    name = display_name(owner, viewer=_user(UserRole.CLIENT), provider_name="ООО Ромашка")
    assert name == "ООО Ромашка"


def test_client_falls_back_to_email_without_name():
    client = _user(UserRole.CLIENT, full_name="", email="client@example.com")
    assert display_name(client, viewer=_user(UserRole.OWNER), provider_name="") == "client@example.com"


# --- непрочитанное ---


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Очередь ответов на execute — по одному на каждый запрос по порядку."""

    def __init__(self, *results):
        self._results = list(results)
        self.added = []

    async def execute(self, _stmt):
        return self._results.pop(0) if self._results else _Result([])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def get(self, _model, _pk):
        return None


CHAT_A = uuid4()
CHAT_B = uuid4()
ME = uuid4()
THEM = uuid4()


@pytest.mark.asyncio
async def test_no_read_mark_means_everything_is_unread():
    session = _FakeSession(
        _Result([]),  # ни одной отметки о прочтении
        _Result([(CHAT_A, T0), (CHAT_A, T0 + timedelta(hours=1))]),
    )
    counts = await unread_counts(session, chat_ids=[CHAT_A], user_id=ME)
    assert counts == {CHAT_A: 2}


@pytest.mark.asyncio
async def test_only_messages_after_the_mark_count():
    session = _FakeSession(
        _Result([(CHAT_A, T0 + timedelta(hours=1))]),
        _Result(
            [
                (CHAT_A, T0),  # прочитано
                (CHAT_A, T0 + timedelta(hours=2)),  # нет
                (CHAT_A, T0 + timedelta(hours=3)),  # нет
            ]
        ),
    )
    counts = await unread_counts(session, chat_ids=[CHAT_A], user_id=ME)
    assert counts == {CHAT_A: 2}


@pytest.mark.asyncio
async def test_fully_read_thread_is_absent_from_counts():
    session = _FakeSession(
        _Result([(CHAT_A, T0 + timedelta(days=1))]),
        _Result([(CHAT_A, T0)]),
    )
    assert await unread_counts(session, chat_ids=[CHAT_A], user_id=ME) == {}


@pytest.mark.asyncio
async def test_counts_are_split_per_thread():
    session = _FakeSession(
        _Result([]),
        _Result([(CHAT_A, T0), (CHAT_B, T0), (CHAT_B, T0 + timedelta(hours=1))]),
    )
    counts = await unread_counts(session, chat_ids=[CHAT_A, CHAT_B], user_id=ME)
    assert counts == {CHAT_A: 1, CHAT_B: 2}


@pytest.mark.asyncio
async def test_empty_input_does_not_touch_the_database():
    session = _FakeSession()
    assert await unread_counts(session, chat_ids=[], user_id=ME) == {}


@pytest.mark.asyncio
async def test_first_read_creates_the_mark():
    session = _FakeSession(_Result([]))
    await mark_read(session, chat_id=CHAT_A, user_id=ME, when=T0)
    assert len(session.added) == 1
    assert session.added[0].last_read_at == T0


@pytest.mark.asyncio
async def test_read_mark_moves_only_forward():
    """Вторая вкладка со старой историей не должна воскрешать прочитанное."""
    existing = SimpleNamespace(chat_id=CHAT_A, user_id=ME, last_read_at=T0 + timedelta(hours=5))
    session = _FakeSession(_Result([existing]))
    await mark_read(session, chat_id=CHAT_A, user_id=ME, when=T0)
    assert existing.last_read_at == T0 + timedelta(hours=5)


@pytest.mark.asyncio
async def test_read_mark_advances_on_newer_time():
    existing = SimpleNamespace(chat_id=CHAT_A, user_id=ME, last_read_at=T0)
    session = _FakeSession(_Result([existing]))
    later = T0 + timedelta(hours=5)
    await mark_read(session, chat_id=CHAT_A, user_id=ME, when=later)
    assert existing.last_read_at == later


# --- доступ к переписке по заявке ---


def _application(created_by=CLIENT_ID, provider_id=PROVIDER):
    return SimpleNamespace(
        id=uuid4(), address_id=uuid4(), provider_id=provider_id, created_by=created_by
    )


def test_client_of_the_application_has_access():
    ensure_application_access(_user(UserRole.CLIENT, user_id=CLIENT_ID), _application())


def test_another_client_has_no_access():
    with pytest.raises(HTTPException) as exc:
        ensure_application_access(_user(UserRole.CLIENT), _application())
    assert exc.value.status_code == 403


def test_assigned_owner_has_access():
    ensure_application_access(_user(UserRole.OWNER, provider_id=PROVIDER), _application())


def test_owner_of_another_organisation_has_no_access():
    with pytest.raises(HTTPException) as exc:
        ensure_application_access(_user(UserRole.OWNER, provider_id=OTHER_PROVIDER), _application())
    assert exc.value.status_code == 403


def test_owner_without_organisation_gets_409():
    with pytest.raises(HTTPException) as exc:
        ensure_application_access(_user(UserRole.OWNER, provider_id=None), _application())
    assert exc.value.status_code == 409


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER])
def test_staff_has_access_to_any_application(role):
    ensure_application_access(_user(role), _application())


# --- ветка по заявке ---


class _AppSession(_FakeSession):
    def __init__(self, *results, author=None):
        super().__init__(*results)
        self._author = author

    async def get(self, _model, _pk):
        return self._author


@pytest.mark.asyncio
async def test_application_reuses_the_existing_thread():
    """Продление не должно заводить вторую ветку — разговор один и тот же."""
    existing = _chat()
    application = SimpleNamespace(
        id=uuid4(), address_id=existing.address_id, created_by=CLIENT_ID
    )
    session = _AppSession(
        _Result([existing]),
        author=_user(UserRole.CLIENT, user_id=CLIENT_ID),
    )
    chat = await resolve_thread_for_application(session, application)
    assert chat is existing
    assert session.added == []


@pytest.mark.asyncio
async def test_application_without_thread_creates_one():
    application = SimpleNamespace(id=uuid4(), address_id=uuid4(), created_by=CLIENT_ID)
    session = _AppSession(_Result([]), author=_user(UserRole.CLIENT, user_id=CLIENT_ID))
    chat = await resolve_thread_for_application(session, application)
    assert chat.address_id == application.address_id
    assert chat.client_user_id == CLIENT_ID
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_application_without_client_account_has_no_thread():
    """Заявку завёл оператор — переписывать не с кем, и это не 500."""
    application = SimpleNamespace(id=uuid4(), address_id=uuid4(), created_by=None)
    session = _AppSession()
    with pytest.raises(HTTPException) as exc:
        await resolve_thread_for_application(session, application)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_application_created_by_staff_has_no_thread():
    application = SimpleNamespace(id=uuid4(), address_id=uuid4(), created_by=uuid4())
    session = _AppSession(author=_user(UserRole.ADMIN))
    with pytest.raises(HTTPException) as exc:
        await resolve_thread_for_application(session, application)
    assert exc.value.status_code == 409
