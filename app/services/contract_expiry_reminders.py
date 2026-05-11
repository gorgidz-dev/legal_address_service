from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationEventKind, NotificationAudience
from app.models.application_event import ApplicationEvent
from app.models.contract import Contract


DEFAULT_MILESTONES_DAYS = (30, 7, 1)


@dataclass(frozen=True)
class ReminderSent:
    contract_id: UUID
    application_id: UUID
    milestone_days: int


def _milestone_titles(days: int) -> tuple[str, str]:
    if days == 30:
        return ("До окончания договора месяц", "Через 30 дней истекает срок договора")
    if days == 7:
        return ("До окончания договора неделя", "Через 7 дней истекает срок договора")
    if days == 1:
        return ("Договор истекает завтра", "Через 1 день истекает срок договора")
    return (
        f"До окончания договора {days} дн.",
        f"Через {days} дней истекает срок договора",
    )


async def _existing_reminder_milestones(
    *,
    db: AsyncSession,
    application_id: UUID,
) -> set[int]:
    result = await db.execute(
        select(ApplicationEvent.payload).where(
            and_(
                ApplicationEvent.application_id == application_id,
                ApplicationEvent.kind == ApplicationEventKind.CONTRACT_EXPIRING.value,
            )
        )
    )
    milestones: set[int] = set()
    for (payload,) in result.all():
        value = (payload or {}).get("milestone_days")
        if isinstance(value, int):
            milestones.add(value)
    return milestones


async def send_contract_expiry_reminders(
    *,
    db: AsyncSession,
    today: date,
    milestones_days: tuple[int, ...] = DEFAULT_MILESTONES_DAYS,
) -> list[ReminderSent]:
    """Отправляет напоминания клиенту по договорам, истекающим через milestones_days.

    Идемпотентность: для одной пары (заявка, milestone) событие создаётся
    ровно один раз — повторный запуск в тот же день ничего не дублирует.
    """
    sent: list[ReminderSent] = []
    for milestone in sorted(set(milestones_days)):
        target_end_date = date.fromordinal(today.toordinal() + milestone)
        result = await db.execute(
            select(Contract).where(Contract.end_date == target_end_date)
        )
        contracts = list(result.scalars().all())
        for contract in contracts:
            already_sent = await _existing_reminder_milestones(
                db=db,
                application_id=contract.application_id,
            )
            if milestone in already_sent:
                continue
            title, message = _milestone_titles(milestone)
            event = ApplicationEvent(
                application_id=contract.application_id,
                kind=ApplicationEventKind.CONTRACT_EXPIRING.value,
                audience=NotificationAudience.CLIENT.value,
                title=title,
                message=(
                    f"{message}. Номер договора {contract.number}, "
                    f"дата окончания {contract.end_date.isoformat()}."
                ),
                payload={
                    "milestone_days": milestone,
                    "contract_id": str(contract.id),
                    "contract_number": contract.number,
                    "end_date": contract.end_date.isoformat(),
                },
                created_at=datetime.now(timezone.utc),
            )
            db.add(event)
            sent.append(
                ReminderSent(
                    contract_id=contract.id,
                    application_id=contract.application_id,
                    milestone_days=milestone,
                )
            )
    return sent
