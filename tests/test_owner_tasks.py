"""Поручения собственнику: права, границы организаций и жизненный цикл."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.enums import OwnerTaskStatus, UserRole
from app.models.owner_task import OwnerTask
from app.models.user_notification import UserNotification
from app.services.owner_tasks import (
    TASK_ASSIGNED_KIND,
    cancel_task,
    complete_task,
    create_task,
    task_read,
)

TODAY = date(2026, 7, 30)
PROVIDER = uuid4()
OTHER_PROVIDER = uuid4()


def _staff():
    return SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value, provider_id=None)


def _owner(provider_id=PROVIDER):
    return SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)


def _task(*, provider_id=PROVIDER, status_value=OwnerTaskStatus.OPEN.value, due_on=None):
    return OwnerTask(
        id=uuid4(),
        provider_id=provider_id,
        address_id=None,
        title="Загрузить фото",
        description=None,
        status=status_value,
        due_on=due_on,
        created_at=datetime.now(timezone.utc),
    )


class _FakeDB:
    """`get` отдаёт заранее подложенные объекты по типу модели."""

    def __init__(self, objects: dict[type, Any] | None = None, users: list[Any] | None = None) -> None:
        self._objects = objects or {}
        self._users = users or []
        self.added: list[Any] = []

    async def get(self, model, _id):
        return self._objects.get(model)

    async def execute(self, _statement):
        users = self._users

        class _R:
            def scalars(self_inner):
                return self_inner

            def all(self_inner):
                return list(users)

        return _R()

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None


def _create(db, **kwargs):
    defaults = dict(
        db=db,
        provider_id=PROVIDER,
        address_id=None,
        title="Загрузить фото помещения",
        description=None,
        due_on=None,
        author=_staff(),
    )
    defaults.update(kwargs)
    return asyncio.run(create_task(**defaults))


# --- постановка ---


def test_task_for_unknown_provider_is_404():
    with pytest.raises(HTTPException) as exc:
        _create(_FakeDB())
    assert exc.value.status_code == 404


def test_address_of_another_provider_is_rejected():
    """Иначе собственник увидел бы у себя адрес чужой организации."""
    from app.models.address import Address
    from app.models.provider import Provider

    db = _FakeDB(
        {
            Provider: SimpleNamespace(id=PROVIDER),
            Address: SimpleNamespace(id=uuid4(), provider_id=OTHER_PROVIDER),
        }
    )
    with pytest.raises(HTTPException) as exc:
        _create(db, address_id=uuid4())
    assert exc.value.status_code == 422


def test_notification_goes_to_every_active_owner_user():
    """Задача, о которой не сказали, будет увидена при следующем заходе — то есть, возможно, никогда."""
    from app.models.provider import Provider

    users = [_owner(), _owner()]
    db = _FakeDB({Provider: SimpleNamespace(id=PROVIDER)}, users=users)
    _create(db)
    notifications = [x for x in db.added if isinstance(x, UserNotification)]
    assert {n.user_id for n in notifications} == {u.id for u in users}
    assert all(n.kind == TASK_ASSIGNED_KIND for n in notifications)
    assert all(n.link_type == "owner_task" for n in notifications)


# --- закрытие ---


def test_owner_closes_own_task():
    task = _task()
    db = _FakeDB({OwnerTask: task})
    user = _owner()
    result = asyncio.run(complete_task(db=db, task_id=task.id, user=user))
    assert result.status == OwnerTaskStatus.DONE.value
    assert result.completed_by == user.id


def test_owner_cannot_close_foreign_task():
    """Чужое поручение — 404, а не 403: чужих задач для него просто не существует."""
    task = _task(provider_id=OTHER_PROVIDER)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(complete_task(db=_FakeDB({OwnerTask: task}), task_id=task.id, user=_owner()))
    assert exc.value.status_code == 404


def test_closing_twice_is_conflict():
    task = _task(status_value=OwnerTaskStatus.DONE.value)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(complete_task(db=_FakeDB({OwnerTask: task}), task_id=task.id, user=_owner()))
    assert exc.value.status_code == 409


def test_owner_without_organisation_gets_conflict():
    task = _task()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            complete_task(db=_FakeDB({OwnerTask: task}), task_id=task.id, user=_owner(provider_id=None))
        )
    assert exc.value.status_code == 409


def test_cancel_marks_cancelled_not_done():
    """Отменено оператором и сделано собственником — разные исходы."""
    task = _task()
    result = asyncio.run(cancel_task(db=_FakeDB({OwnerTask: task}), task_id=task.id))
    assert result.status == OwnerTaskStatus.CANCELLED.value


# --- отображение срока ---


def test_due_days_counted_for_open_task():
    task = _task(due_on=date(2026, 8, 2))
    assert task_read(task, address_label=None, today=TODAY).days_until_due == 3


def test_overdue_is_negative():
    task = _task(due_on=date(2026, 7, 28))
    assert task_read(task, address_label=None, today=TODAY).days_until_due == -2


def test_closed_task_hides_the_countdown():
    """У закрытой задачи «просрочено на 5 дн.» только сбивает с толку."""
    task = _task(due_on=date(2026, 7, 20), status_value=OwnerTaskStatus.DONE.value)
    assert task_read(task, address_label=None, today=TODAY).days_until_due is None
