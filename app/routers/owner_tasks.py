"""Поручения собственнику: ручки оператора и собственника.

Разнесены по двум префиксам, а не по одному с проверкой роли внутри: право
ставить задачу и право её закрывать принадлежат разным ролям, и это должно
быть видно по зависимости роутера, а не по коду обработчика.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_owner, require_staff
from app.database import get_db
from app.enums import OWNER_TASK_TEMPLATES
from app.models.user import User
from app.schemas.owner_task import OwnerTaskCreate, OwnerTaskRead, OwnerTaskTemplate
from app.services.owner_tasks import (
    cancel_task,
    complete_task,
    create_task,
    list_tasks_for_owner,
    list_tasks_for_staff,
    task_read,
)

owner_router = APIRouter(prefix="/owner/tasks", tags=["owner-tasks"])
staff_router = APIRouter(
    prefix="/admin/owner-tasks",
    tags=["owner-tasks"],
    dependencies=[Depends(require_staff)],
)


# ---------------------------- кабинет собственника ----------------------------


@owner_router.get("", response_model=list[OwnerTaskRead], summary="Мои поручения")
async def my_tasks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[OwnerTaskRead]:
    if user.provider_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя"
        )
    return await list_tasks_for_owner(db=db, provider_id=user.provider_id)


@owner_router.post(
    "/{task_id}/complete",
    response_model=OwnerTaskRead,
    summary="Отметить поручение выполненным",
)
async def complete(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> OwnerTaskRead:
    task = await complete_task(db=db, task_id=task_id, user=user)
    await db.commit()
    await db.refresh(task)
    return task_read(task, address_label=None, today=date.today())


# ------------------------------- оператор -------------------------------


@staff_router.get(
    "/templates",
    response_model=list[OwnerTaskTemplate],
    summary="Заготовки частых поручений",
)
async def templates() -> list[OwnerTaskTemplate]:
    return [
        OwnerTaskTemplate(title=title, description=description)
        for title, description in OWNER_TASK_TEMPLATES
    ]


@staff_router.get("", response_model=list[OwnerTaskRead], summary="Поручения собственникам")
async def list_all(
    provider_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[OwnerTaskRead]:
    return await list_tasks_for_staff(db=db, provider_id=provider_id)


@staff_router.post(
    "",
    response_model=OwnerTaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Поставить поручение",
)
async def create(
    payload: OwnerTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_staff),
) -> OwnerTaskRead:
    task = await create_task(
        db=db,
        provider_id=payload.provider_id,
        address_id=payload.address_id,
        title=payload.title,
        description=payload.description,
        due_on=payload.due_on,
        author=user,
    )
    await db.commit()
    await db.refresh(task)
    return task_read(task, address_label=None, today=date.today())


@staff_router.post(
    "/{task_id}/cancel",
    response_model=OwnerTaskRead,
    summary="Отменить поручение",
)
async def cancel(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> OwnerTaskRead:
    task = await cancel_task(db=db, task_id=task_id)
    await db.commit()
    await db.refresh(task)
    return task_read(task, address_label=None, today=date.today())
