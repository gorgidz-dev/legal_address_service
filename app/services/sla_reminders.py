"""Напоминания по внутренним срокам этапов заявки.

Дедлайн сам по себе ничего не ускоряет — нужен тот, кто о нём напомнит. Этот
сервис проходит по заявкам, застрявшим в статусе со сроком, и создаёт события:
собственнику — «пора», оператору — «собственник тянет».

Клиенту не адресуется ни одно событие: сроки внутренние (решение владельца от
30.07.2026). Аудитория здесь всегда OWNER или ADMIN.

Отличие от contract_expiry_reminders, с которого списан подход: у договора одна
неподвижная дата окончания, а срок этапа меняется при каждой смене статуса.
Поэтому идемпотентность здесь ключуется не только на веху, но и на сам дедлайн:
после перехода в новый статус срок другой — и напоминания по нему пойдут заново,
а повторный прогон в тот же день по тому же сроку ничего не продублирует.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationEventKind, NotificationAudience, UserRole
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.services.application_sla import SLA_RULES, sla_owner_role

#: Вехи в днях ДО срока. 0 — «сегодня последний день».
BEFORE_MILESTONES = (1, 0)
#: Вехи в днях ПОСЛЕ срока. Не каждый день: ежедневная долбёжка читается как
#: спам и её перестают открывать.
OVERDUE_MILESTONES = (1, 3, 7)


@dataclass(frozen=True)
class DeadlineReminder:
    application_id: UUID
    #: Отрицательное — просрочено на столько дней, 0 и больше — осталось.
    days_left: int
    audience: NotificationAudience


def _texts(days_left: int, *, for_owner: bool) -> tuple[str, str]:
    """Заголовок и текст. Собственнику — просьба, оператору — факт."""
    if days_left > 0:
        if for_owner:
            return ("Срок по заявке истекает завтра", "Завтра последний день по этой заявке.")
        return ("Срок по заявке истекает завтра", "Собственник ещё не отработал заявку.")
    if days_left == 0:
        if for_owner:
            return ("Сегодня последний день по заявке", "Сегодня истекает срок по этой заявке.")
        return ("Сегодня последний день по заявке", "Собственник ещё не отработал заявку.")
    overdue = -days_left
    word = "день" if overdue == 1 else "дн."
    if for_owner:
        return (
            f"Заявка просрочена на {overdue} {word}",
            "Срок по заявке вышел. Просим отработать её сегодня.",
        )
    return (
        f"Собственник просрочил заявку на {overdue} {word}",
        "Срок этапа вышел, собственник не отработал заявку.",
    )


async def _already_sent(
    *,
    db: AsyncSession,
    application_id: UUID,
    due_at_iso: str,
) -> set[int]:
    """Вехи, по которым напоминание для ЭТОГО дедлайна уже создавалось."""
    result = await db.execute(
        select(ApplicationEvent.payload).where(
            and_(
                ApplicationEvent.application_id == application_id,
                ApplicationEvent.kind == ApplicationEventKind.STAGE_DEADLINE.value,
            )
        )
    )
    seen: set[int] = set()
    for (payload,) in result.all():
        payload = payload or {}
        if payload.get("due_at") != due_at_iso:
            continue
        value = payload.get("days_left")
        if isinstance(value, int):
            seen.add(value)
    return seen


def _milestone_for(days_left: int) -> int | None:
    """Веха, под которую подпадает текущий остаток, или None."""
    if days_left in BEFORE_MILESTONES:
        return days_left
    overdue = -days_left
    if overdue in OVERDUE_MILESTONES:
        return days_left
    return None


async def send_stage_deadline_reminders(
    *,
    db: AsyncSession,
    now: datetime | None = None,
) -> list[DeadlineReminder]:
    """Создаёт напоминания по заявкам, у которых подходит или вышел срок этапа."""
    now = now or datetime.now(timezone.utc)
    sent: list[DeadlineReminder] = []

    result = await db.execute(
        select(Application).where(
            and_(
                Application.sla_due_at.is_not(None),
                # Статус мог уйти вперёд, а срок остаться — берём только те,
                # где по текущему статусу действительно кого-то ждут.
                Application.status.in_(tuple(SLA_RULES)),
            )
        )
    )

    for application in result.scalars().all():
        due_at = application.sla_due_at
        if due_at is None:
            continue
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)

        days_left = (due_at.date() - now.date()).days
        milestone = _milestone_for(days_left)
        if milestone is None:
            continue

        due_at_iso = due_at.isoformat()
        if milestone in await _already_sent(
            db=db, application_id=application.id, due_at_iso=due_at_iso
        ):
            continue

        role = sla_owner_role(application.status)
        # Собственнику пишем, когда ждут его. Оператору — когда ждут нас, а
        # также на любой просрочке собственника: «мы ему напомним» работает,
        # только если оператор видит, что напоминать пора.
        audiences: list[NotificationAudience] = []
        if role is UserRole.OWNER:
            audiences.append(NotificationAudience.OWNER)
            if days_left < 0:
                audiences.append(NotificationAudience.ADMIN)
        else:
            audiences.append(NotificationAudience.ADMIN)

        for audience in audiences:
            title, message = _texts(
                days_left, for_owner=audience is NotificationAudience.OWNER
            )
            db.add(
                ApplicationEvent(
                    application_id=application.id,
                    kind=ApplicationEventKind.STAGE_DEADLINE.value,
                    audience=audience.value,
                    title=title,
                    message=message,
                    payload={
                        "days_left": milestone,
                        "due_at": due_at_iso,
                        "status": application.status,
                    },
                    created_at=now,
                )
            )
            sent.append(
                DeadlineReminder(
                    application_id=application.id,
                    days_left=milestone,
                    audience=audience,
                )
            )

    return sent
