"""Напоминание «пора сверить регистрацию» по дате из расписки ИФНС.

Статус-трекер (этап 6): клиент загружает расписку с датой предстоящей
регистрации. Когда дата наступила, а регистрация не подтверждена, админу —
«сверьте с ЕГРЮЛ» (от подтверждения зависит выплата собственнику). От клиента
больше ничего не нужно: первичная регистрация сверяется по названию и адресу,
смена адреса — по ИНН из заявки (решение владельца 13.10.2026).

Идемпотентность: на одну дату — одно напоминание. Клиент загрузил новую
расписку с другой датой — по новой дате напоминание идёт заново.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationEventKind, NotificationAudience
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.services.notification_events import create_application_event
from app.services.owner_payouts import REGISTRATION_ALLOWED

#: Дата из расписки — московская; сервер живёт в UTC.
MOSCOW = timezone(timedelta(hours=3))
REMINDER_KEY = "registration_check_due"


async def _reminded(db: AsyncSession, application_id: Any) -> set[tuple[str, str]]:
    """(аудитория, дата), по которым напоминание уже создавалось (метка в payload)."""
    rows = await db.execute(
        select(ApplicationEvent.audience, ApplicationEvent.payload).where(
            ApplicationEvent.application_id == application_id,
            ApplicationEvent.payload.has_key(REMINDER_KEY),
        )
    )
    seen: set[tuple[str, str]] = set()
    for audience, payload in rows.all():
        value = (payload or {}).get(REMINDER_KEY)
        if isinstance(value, str):
            seen.add((audience, value))
    return seen


async def send_registration_check_reminders(*, db: AsyncSession, now: datetime) -> list[ApplicationEvent]:
    today = now.astimezone(MOSCOW).date()
    applications = (
        await db.execute(
            select(Application).where(
                Application.registration_expected_on.is_not(None),
                Application.registration_expected_on <= today,
                Application.registration_confirmed_at.is_(None),
                Application.status.in_(REGISTRATION_ALLOWED),
            )
        )
    ).scalars().all()

    sent: list[ApplicationEvent] = []
    for application in applications:
        due = application.registration_expected_on.isoformat()
        when = application.registration_expected_on.strftime("%d.%m.%Y")
        seen = await _reminded(db, application.id)
        payload = {REMINDER_KEY: due}
        if (NotificationAudience.ADMIN.value, due) not in seen:
            sent.append(
                await create_application_event(
                    db=db,
                    application_id=application.id,
                    kind=ApplicationEventKind.STAGE_DEADLINE,
                    audience=NotificationAudience.ADMIN,
                    title="Пора сверить регистрацию",
                    message=(
                        f"По расписке ИФНС регистрация ожидалась {when}. Сверьте её с ЕГРЮЛ — "
                        "от подтверждения зависит выплата собственнику."
                    ),
                    payload=payload,
                )
            )
    return sent
