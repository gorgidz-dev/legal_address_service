"""Поручения собственнику: постановка, выдача, закрытие.

Правило доступа одно и живёт здесь: оператор ставит и отменяет, собственник
видит и закрывает только свои. Разнеси проверку по ручкам — и однажды
появится ручка, через которую видно чужие задачи.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import OwnerTaskStatus, UserRole
from app.models.address import Address
from app.models.owner_task import OwnerTask
from app.models.provider import Provider
from app.models.user import User
from app.models.user_notification import UserNotification
from app.schemas.owner_task import OwnerTaskRead

#: Вид уведомления о новом поручении.
TASK_ASSIGNED_KIND = "owner_task_assigned"


def task_read(task: OwnerTask, *, address_label: str | None, today: date) -> OwnerTaskRead:
    # Срок показываем только у открытых: у закрытой задачи «просрочено на 5 дн.»
    # сбивает с толку — её уже закрыли.
    days = None
    if task.due_on is not None and task.status == OwnerTaskStatus.OPEN.value:
        days = (task.due_on - today).days
    return OwnerTaskRead(
        id=task.id,
        provider_id=task.provider_id,
        address_id=task.address_id,
        address_label=address_label,
        title=task.title,
        description=task.description,
        status=OwnerTaskStatus(task.status),
        due_on=task.due_on,
        days_until_due=days,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


async def _labels_for(db: AsyncSession, tasks: list[OwnerTask]) -> dict[UUID, str]:
    address_ids = {task.address_id for task in tasks if task.address_id}
    if not address_ids:
        return {}
    result = await db.execute(
        select(Address.id, Address.full_address).where(Address.id.in_(address_ids))
    )
    return {row[0]: row[1] for row in result.all()}


async def list_tasks_for_owner(
    *, db: AsyncSession, provider_id: UUID, today: date | None = None
) -> list[OwnerTaskRead]:
    today = today or date.today()
    result = await db.execute(
        select(OwnerTask)
        .where(OwnerTask.provider_id == provider_id)
        # Открытые сверху, внутри — по сроку; бессрочные в конец группы.
        .order_by(
            (OwnerTask.status != OwnerTaskStatus.OPEN.value),
            OwnerTask.due_on.asc().nullslast(),
            OwnerTask.created_at.desc(),
        )
    )
    tasks = list(result.scalars().all())
    labels = await _labels_for(db, tasks)
    return [
        task_read(task, address_label=labels.get(task.address_id) if task.address_id else None, today=today)
        for task in tasks
    ]


async def list_tasks_for_staff(
    *, db: AsyncSession, provider_id: UUID | None = None, today: date | None = None
) -> list[OwnerTaskRead]:
    today = today or date.today()
    statement = select(OwnerTask).order_by(
        (OwnerTask.status != OwnerTaskStatus.OPEN.value),
        OwnerTask.due_on.asc().nullslast(),
        OwnerTask.created_at.desc(),
    )
    if provider_id is not None:
        statement = statement.where(OwnerTask.provider_id == provider_id)
    result = await db.execute(statement)
    tasks = list(result.scalars().all())
    labels = await _labels_for(db, tasks)
    return [
        task_read(task, address_label=labels.get(task.address_id) if task.address_id else None, today=today)
        for task in tasks
    ]


async def create_task(
    *,
    db: AsyncSession,
    provider_id: UUID,
    address_id: UUID | None,
    title: str,
    description: str | None,
    due_on: date | None,
    author: User | object,
) -> OwnerTask:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собственник не найден")

    if address_id is not None:
        address = await db.get(Address, address_id)
        if address is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
        # Задача про чужой адрес — почти всегда опечатка в форме, и она бы
        # показала собственнику адрес другой организации.
        if address.provider_id != provider_id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Адрес принадлежит другой организации",
            )

    task = OwnerTask(
        provider_id=provider_id,
        address_id=address_id,
        title=title.strip(),
        description=(description or "").strip() or None,
        status=OwnerTaskStatus.OPEN.value,
        due_on=due_on,
        created_by=getattr(author, "id", None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(task)
    await db.flush()

    # Уведомление сразу: задача, о которой не сказали, — это задача, которую
    # увидят при следующем заходе в кабинет, то есть, возможно, никогда.
    users = await db.execute(
        select(User).where(
            User.provider_id == provider_id,
            User.role == UserRole.OWNER.value,
            User.is_active.is_(True),
        )
    )
    body = task.description or "Откройте раздел «Задачи» в кабинете."
    for user in users.scalars().all():
        db.add(
            UserNotification(
                user_id=user.id,
                kind=TASK_ASSIGNED_KIND,
                title=f"Новое поручение: {task.title}",
                body=body,
                link_type="owner_task",
                link_id=task.id,
            )
        )
    return task


async def _load_own_task(
    *, db: AsyncSession, task_id: UUID, provider_id: UUID
) -> OwnerTask:
    task = await db.get(OwnerTask, task_id)
    if task is None or task.provider_id != provider_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поручение не найдено")
    return task


async def complete_task(
    *, db: AsyncSession, task_id: UUID, user: User | object
) -> OwnerTask:
    provider_id = getattr(user, "provider_id", None)
    if provider_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя"
        )
    task = await _load_own_task(db=db, task_id=task_id, provider_id=provider_id)
    if task.status != OwnerTaskStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Поручение уже закрыто")
    task.status = OwnerTaskStatus.DONE.value
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by = getattr(user, "id", None)
    return task


async def cancel_task(*, db: AsyncSession, task_id: UUID) -> OwnerTask:
    task = await db.get(OwnerTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Поручение не найдено")
    if task.status != OwnerTaskStatus.OPEN.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Поручение уже закрыто")
    task.status = OwnerTaskStatus.CANCELLED.value
    task.completed_at = datetime.now(timezone.utc)
    return task
