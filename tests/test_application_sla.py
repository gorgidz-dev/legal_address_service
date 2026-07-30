"""Внутренние сроки этапов заявки.

Два предмета проверки: арифметика рабочих дней (3 рабочих дня из оферты не
должны превращаться в календарные) и граница видимости — клиент срок видеть
не должен.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.enums import ApplicationStatus, UserRole
from app.schemas.application import ApplicationRead
from app.schemas.client_dashboard import ClientApplicationRead
from app.schemas.owner_dashboard import OwnerApplicationRead
from app.services.application_sla import (
    DEADLINE_HOUR_UTC,
    SLA_RULES,
    add_business_days,
    apply_sla,
    sla_due_for_status,
    sla_owner_role,
)


def _at(year: int, month: int, day: int, hour: int = 9) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


# 2026-07-30 — четверг, 2026-07-31 — пятница, 01-02.08 — выходные.
THURSDAY = _at(2026, 7, 30)
FRIDAY = _at(2026, 7, 31)


def test_business_days_skip_weekend():
    """Пятница + 1 рабочий день = понедельник, а не суббота."""
    assert add_business_days(FRIDAY, 1).date() == _at(2026, 8, 3).date()


def test_three_business_days_from_thursday_lands_on_tuesday():
    """Три рабочих дня из оферты: чт → пт, пн, вт."""
    assert add_business_days(THURSDAY, 3).date() == _at(2026, 8, 4).date()


def test_deadline_is_end_of_day_not_time_of_entry():
    """Заявка, назначенная в 09:05, не должна просрочиться в 09:05."""
    due = add_business_days(_at(2026, 7, 30, hour=9), 1)
    assert due.hour == DEADLINE_HOUR_UTC
    assert due.minute == 0


def test_zero_business_days_is_same_day_end():
    assert add_business_days(THURSDAY, 0).date() == THURSDAY.date()


def test_negative_days_rejected():
    with pytest.raises(ValueError):
        add_business_days(THURSDAY, -1)


@pytest.mark.parametrize("status", sorted(SLA_RULES))
def test_every_rule_produces_a_deadline(status):
    assert sla_due_for_status(status, now=THURSDAY) is not None
    assert sla_owner_role(status) in {UserRole.OWNER, UserRole.ADMIN}


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.COMPLETED.value,
        ApplicationStatus.CANCELLED.value,
        ApplicationStatus.READY_FOR_CLIENT.value,
        ApplicationStatus.NEEDS_CLIENT_FIX.value,
    ],
)
def test_terminal_and_client_side_statuses_have_no_deadline(status):
    """Ждать нечего — срок снимается, иначе завершённая заявка вечно просрочена."""
    assert sla_due_for_status(status, now=THURSDAY) is None
    assert sla_owner_role(status) is None


def test_apply_sla_clears_deadline_on_terminal_status():
    application = SimpleNamespace(
        status=ApplicationStatus.DOCUMENTS_PREPARING.value, sla_due_at=None
    )
    apply_sla(application, now=THURSDAY)
    assert application.sla_due_at is not None

    application.status = ApplicationStatus.COMPLETED.value
    apply_sla(application, now=THURSDAY)
    assert application.sla_due_at is None


def test_owner_deadline_is_shorter_for_revision_than_first_preparation():
    """Доработка — это правка уже собранного, на неё даётся меньше."""
    prepare = SLA_RULES[ApplicationStatus.DOCUMENTS_PREPARING.value][1]
    revision = SLA_RULES[ApplicationStatus.DOCUMENTS_REVISION.value][1]
    assert revision < prepare


def test_offer_promises_three_business_days_for_owner_confirmation():
    """П. 3.2 оферты: «Срок первичного согласования — до 3 рабочих дней»."""
    role, days = SLA_RULES[ApplicationStatus.ASSIGNED_TO_OWNER.value]
    assert role is UserRole.OWNER
    assert days == 3


def test_client_schema_has_no_deadline_field():
    """Главная граница: клиенту срок не показывается."""
    assert "sla_due_at" not in ClientApplicationRead.model_fields


def test_staff_and_owner_schemas_expose_deadline():
    assert "sla_due_at" in ApplicationRead.model_fields
    assert "sla_due_at" in OwnerApplicationRead.model_fields
