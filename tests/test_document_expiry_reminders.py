"""Напоминания об истекающих документах адреса.

Канал здесь другой, чем у двух остальных рассылок: у документа нет заявки,
поэтому уведомления персональные (UserNotification), а не события заявки.
Проверяется именно это плюс идемпотентность по паре (документ, веха).
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.enums import AddressDocumentKind, UserRole
from app.models.user_notification import UserNotification
from app.services.document_expiry_reminders import (
    NOTIFICATION_KIND,
    send_document_expiry_reminders,
)

TODAY = date(2026, 7, 30)
PROVIDER = uuid4()


def _document(*, expires_in: int):
    return SimpleNamespace(
        id=uuid4(),
        kind=AddressDocumentKind.OWNERSHIP_CERTIFICATE.value,
        title="Свидетельство 77-АБ 123456",
        expires_at=TODAY + timedelta(days=expires_in),
    )


def _address():
    return SimpleNamespace(
        id=uuid4(), provider_id=PROVIDER, full_address="г. Москва, ул. Тверская, д. 1"
    )


def _owner_user():
    return SimpleNamespace(
        id=uuid4(), provider_id=PROVIDER, role=UserRole.OWNER.value, is_active=True
    )


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeDB:
    """Три вида запросов: документы, пользователи и уже отправленные kind-ы."""

    def __init__(self, pairs: list[tuple[Any, Any]], users: list[Any]) -> None:
        self._pairs = pairs
        self._users = users
        self.added: list[UserNotification] = []

    async def execute(self, statement):
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if "FROM address_documents" in compiled:
            target = compiled.split("expires_at = '")[1][:10]
            return _Rows(
                [(d, a) for d, a in self._pairs if d.expires_at.isoformat() == target]
            )
        if "FROM users" in compiled:
            return _Rows(self._users)
        if "FROM user_notifications" in compiled:
            marker = "link_id = '"
            idx = compiled.find(marker)
            doc_hex = compiled[idx + len(marker):][:32] if idx >= 0 else ""
            return _Rows(
                [
                    (n.kind,)
                    for n in self.added
                    if str(n.link_id).replace("-", "") == doc_hex
                ]
            )
        raise AssertionError(f"Неожиданный запрос: {compiled!r}")

    def add(self, item: Any) -> None:
        self.added.append(item)


def _run(db: _FakeDB, milestones=(30, 7, 1, 0)):
    return asyncio.run(
        send_document_expiry_reminders(db=db, today=TODAY, milestones_days=milestones)
    )


def test_no_reminder_for_document_outside_milestones():
    db = _FakeDB([(_document(expires_in=15), _address())], [_owner_user()])
    assert _run(db) == []


def test_reminder_on_milestone():
    db = _FakeDB([(_document(expires_in=7), _address())], [_owner_user()])
    sent = _run(db)
    assert [item.milestone_days for item in sent] == [7]
    assert db.added[0].kind == f"{NOTIFICATION_KIND}:7"


def test_expiring_today_is_covered():
    """Веха 0 нужна: без неё документ молча протухал в день истечения."""
    db = _FakeDB([(_document(expires_in=0), _address())], [_owner_user()])
    assert [item.milestone_days for item in _run(db)] == [0]


def test_every_active_owner_user_is_notified():
    users = [_owner_user(), _owner_user()]
    db = _FakeDB([(_document(expires_in=1), _address())], users)
    sent = _run(db)
    assert {item.user_id for item in sent} == {u.id for u in users}


def test_second_run_same_day_does_not_duplicate():
    db = _FakeDB([(_document(expires_in=30), _address())], [_owner_user()])
    assert _run(db)
    assert _run(db) == []


def test_different_milestones_are_sent_separately():
    """За 30 дней и за 7 — это два разных напоминания об одном документе."""
    document = _document(expires_in=30)
    db = _FakeDB([(document, _address())], [_owner_user()])
    assert _run(db, milestones=(30,))

    document.expires_at = TODAY + timedelta(days=7)
    assert _run(db, milestones=(7,)), "веха 7 не должна считаться уже отправленной"


def test_notification_links_to_the_document():
    db = _FakeDB([(_document(expires_in=1), _address())], [_owner_user()])
    _run(db)
    assert db.added[0].link_type == "address_document"


def test_address_is_named_in_the_message():
    """У собственника несколько адресов — без адреса уведомление бесполезно."""
    address = _address()
    db = _FakeDB([(_document(expires_in=1), address)], [_owner_user()])
    _run(db)
    assert address.full_address in db.added[0].body
