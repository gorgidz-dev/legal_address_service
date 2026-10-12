"""application_events.kind: разрешить stage_deadline

Вид события STAGE_DEADLINE (напоминания по срокам этапов, July 2026,
app/services/sla_reminders.py) появился в коде без миграции: ограничение
ck_application_events_kind_valid его не пускало, и вставка напоминания падала
CheckViolation. Юнит-тесты на подставной сессии этого не видят — поймал смоук
статус-трекера на настоящем Postgres (13.10.2026).

Расширение списка — аддитивное; откат возвращает прежний список (и упадёт, если
такие события уже есть — это правильно, их нельзя молча потерять).

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KIND_VALUES_OLD = (
    "created",
    "status_changed",
    "comment_added",
    "document_uploaded",
    "document_approved",
    "correction_requested",
    "dispute_opened",
    "cancelled",
    "contract_expiring",
)
#: Полный список после этой миграции — совпадает с app.enums.ApplicationEventKind
#: (tests/test_event_kind_constraint.py следит, чтобы так и оставалось).
KIND_VALUES = KIND_VALUES_OLD + ("stage_deadline",)


def _check(values: Sequence[str]) -> str:
    return "kind IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_application_events_kind_valid"), "application_events", type_="check")
    op.create_check_constraint(
        op.f("ck_application_events_kind_valid"), "application_events", _check(KIND_VALUES)
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_application_events_kind_valid"), "application_events", type_="check")
    op.create_check_constraint(
        op.f("ck_application_events_kind_valid"), "application_events", _check(KIND_VALUES_OLD)
    )
