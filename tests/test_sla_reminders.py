"""Напоминания по внутренним срокам этапов.

База не нужна: сервис делает два запроса — за заявками и за уже созданными
событиями, — и оба подменяются фейком, как в test_contract_expiry_reminders.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from app.enums import ApplicationEventKind, ApplicationStatus, NotificationAudience
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.services.sla_reminders import send_stage_deadline_reminders

NOW = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)


def _application(*, due_in_days: int, status: str = ApplicationStatus.DOCUMENTS_PREPARING.value):
    application = Application(
        id=uuid4(),
        provider_id=uuid4(),
        address_id=uuid4(),
        status=status,
    )
    application.sla_due_at = NOW + timedelta(days=due_in_days)
    return application


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _PayloadResult:
    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = payloads

    def all(self) -> list[tuple[Any]]:
        return [(p,) for p in self._payloads]


class _FakeDB:
    """Отдаёт заявки на запрос к applications и payload-ы на запрос к событиям."""

    def __init__(self, applications: list[Application]) -> None:
        self._applications = applications
        self.added: list[ApplicationEvent] = []

    async def execute(self, statement):
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if "FROM applications" in compiled:
            return _Result(self._applications)
        if "FROM application_events" in compiled:
            marker = "application_id = "
            idx = compiled.find(marker)
            assert idx >= 0, compiled
            quoted = compiled[idx + len(marker):]
            start = quoted.find("'") + 1
            app_id = UUID(quoted[start: quoted.find("'", start)])
            return _PayloadResult(
                [
                    e.payload
                    for e in self.added
                    if UUID(str(e.application_id)) == app_id
                    and e.kind == ApplicationEventKind.STAGE_DEADLINE.value
                ]
            )
        raise AssertionError(f"Неожиданный запрос: {compiled!r}")

    def add(self, item: Any) -> None:
        self.added.append(item)


def _run(db: _FakeDB, now: datetime = NOW):
    return asyncio.run(send_stage_deadline_reminders(db=db, now=now))


def test_no_reminder_when_deadline_is_far():
    db = _FakeDB([_application(due_in_days=5)])
    assert _run(db) == []


def test_reminder_on_last_day_goes_to_owner_only():
    db = _FakeDB([_application(due_in_days=0)])
    sent = _run(db)
    assert [r.audience for r in sent] == [NotificationAudience.OWNER]


def test_overdue_notifies_owner_and_operator():
    """Смысл всей затеи: оператор должен узнать, что собственник тянет."""
    db = _FakeDB([_application(due_in_days=-1)])
    sent = _run(db)
    assert {r.audience for r in sent} == {
        NotificationAudience.OWNER,
        NotificationAudience.ADMIN,
    }


def test_client_never_receives_deadline_events():
    """Сроки внутренние — клиенту не адресуется ни одно событие."""
    db = _FakeDB([_application(due_in_days=d) for d in (1, 0, -1, -3, -7)])
    _run(db)
    audiences = {e.audience for e in db.added}
    assert NotificationAudience.CLIENT.value not in audiences


def test_second_run_same_day_does_not_duplicate():
    db = _FakeDB([_application(due_in_days=-1)])
    first = _run(db)
    second = _run(db)
    assert first and second == []


def test_new_deadline_after_status_change_reminds_again():
    """Смена статуса меняет срок — по новому этапу отсчёт начинается заново."""
    application = _application(due_in_days=-1)
    db = _FakeDB([application])
    assert _run(db)

    application.status = ApplicationStatus.DOCUMENTS_REVISION.value
    application.sla_due_at = NOW + timedelta(days=-1, hours=1)
    assert _run(db), "новый дедлайн — новое напоминание"


def test_operator_side_deadline_does_not_pester_owner():
    """Проверку загруженного комплекта делаем мы — собственника это не касается."""
    db = _FakeDB([_application(due_in_days=0, status=ApplicationStatus.DOCUMENTS_REVIEW.value)])
    sent = _run(db)
    assert [r.audience for r in sent] == [NotificationAudience.ADMIN]


def test_only_configured_overdue_milestones_fire():
    """На 2-й и 4-й день напоминания нет: вехи 1, 3, 7, чтобы не спамить."""
    for days in (-2, -4, -5):
        assert _run(_FakeDB([_application(due_in_days=days)])) == [], days
    for days in (-1, -3, -7):
        assert _run(_FakeDB([_application(due_in_days=days)])), days
