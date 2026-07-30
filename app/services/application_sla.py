"""Внутренние сроки этапов заявки.

Зачем. Заявка может неделю простоять в статусе «собственник готовит документы»,
и до этой правки заметить это было нечем: у заявки не было ни одной даты,
означающей «к этому моменту должно быть сделано». Из-за этого в очереди
оператора не было колонки срока, а напоминать собственнику было не от чего
считать.

Сроки ВНУТРЕННИЕ. Клиенту они не показываются: решение владельца от 30.07.2026 —
«если собственник будет тянуть, мы ему напомним, клиенту об этом знать не нужно».
Поэтому поле попадает в схемы оператора и собственника, но не в клиентскую.

Срок считается в РАБОЧИХ днях. Календарные дали бы дедлайн в воскресенье,
а «3 рабочих дня» на согласование — обязательство из п. 3.2 оферты, и его
арифметика должна совпадать с тем, что там написано.

Производственный календарь не учитывается: переносы и праздники требуют
отдельного справочника, а без него лучше честная суббота-воскресенье, чем
выдуманные выходные.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from app.enums import ApplicationStatus, UserRole

# Кто должен действовать в этом статусе и сколько рабочих дней на это есть.
#
# ASSIGNED_TO_OWNER — 3 дня не выбраны, а взяты из оферты: «Срок первичного
# согласования — до 3 рабочих дней». Меняя это число, надо менять и оферту.
SLA_RULES: dict[str, tuple[UserRole, int]] = {
    ApplicationStatus.ASSIGNED_TO_OWNER.value: (UserRole.OWNER, 3),
    ApplicationStatus.DOCUMENTS_PREPARING.value: (UserRole.OWNER, 2),
    ApplicationStatus.DOCUMENTS_REVISION.value: (UserRole.OWNER, 1),
    ApplicationStatus.DOCUMENTS_REVIEW.value: (UserRole.ADMIN, 1),
    ApplicationStatus.ADMIN_REVIEW.value: (UserRole.ADMIN, 1),
}

#: Час, на который ставится дедлайн, — конец рабочего дня по Москве (UTC+3).
DEADLINE_HOUR_UTC = 15


def _is_workday(value: datetime) -> bool:
    return value.weekday() < 5


def add_business_days(start: datetime, days: int) -> datetime:
    """Прибавляет рабочие дни, пропуская субботу и воскресенье.

    Отсчёт начинается со следующего рабочего дня: заявка, назначенная в пятницу
    вечером, получает срок не в понедельник утром, а через `days` рабочих дней
    от понедельника.
    """
    if days < 0:
        raise ValueError("Срок не может быть отрицательным")
    cursor = start
    remaining = days
    while remaining > 0:
        cursor += timedelta(days=1)
        if _is_workday(cursor):
            remaining -= 1
    # Дедлайн — конец рабочего дня, а не тот же час, что и постановка: иначе
    # заявка, назначенная в 09:05, просрочивалась бы в 09:05, посреди дня.
    return datetime.combine(cursor.date(), time(hour=DEADLINE_HOUR_UTC), tzinfo=timezone.utc)


def sla_due_for_status(status: str, *, now: datetime) -> datetime | None:
    """Дедлайн для статуса или None, если в этом статусе никто ничего не должен.

    None — это не «бессрочно», а «ждать нечего»: заявка завершена, отменена или
    мяч на стороне клиента. Такие статусы дедлайн снимают, чтобы завершённая
    заявка не висела в очереди просроченной вечно.
    """
    rule = SLA_RULES.get(status)
    if rule is None:
        return None
    _, days = rule
    return add_business_days(now, days)


def sla_owner_role(status: str) -> UserRole | None:
    """Кто именно должен действовать — собственник или мы."""
    rule = SLA_RULES.get(status)
    return rule[0] if rule else None


def apply_sla(application, *, now: datetime | None = None) -> None:
    """Проставляет заявке дедлайн под её текущий статус.

    Вызывается после каждой смены статуса. Идемпотентна по смыслу: повторный
    вызов на том же статусе просто пересчитает срок от «сейчас», поэтому
    вызывать её надо один раз на переход, а не в цикле обновления.
    """
    application.sla_due_at = sla_due_for_status(
        application.status, now=now or datetime.now(timezone.utc)
    )
