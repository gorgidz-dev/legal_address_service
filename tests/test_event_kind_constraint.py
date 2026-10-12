"""Каждый вид события из кода должен быть разрешён ограничением в базе.

STAGE_DEADLINE появился в app.enums без миграции, и вставка напоминания падала
CheckViolation на настоящем Postgres (подставные сессии этого не видят).
Новый вид события = новая миграция, расширяющая ck_application_events_kind_valid,
и обновление этого теста на неё.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.enums import ApplicationEventKind

LATEST = Path(__file__).resolve().parents[1] / "alembic/versions/2026_10_13_0200_0038_event_kind_stage_deadline.py"


def test_every_event_kind_is_allowed_by_latest_migration() -> None:
    spec = importlib.util.spec_from_file_location("migration_0038", LATEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.KIND_VALUES) == {kind.value for kind in ApplicationEventKind}
