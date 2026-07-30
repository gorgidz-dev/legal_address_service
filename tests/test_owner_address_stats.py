"""Отдача по адресам собственника.

База не нужна: агрегат собирается одним запросом, и здесь проверяется разбор
его результата — перевод копеек в рубли, нули для адресов без оплат и то, что
в выручку не попадает ничего, кроме подтверждённых платежей.

Сам SQL проверяется отдельно: тест ниже собирает выражение и смотрит, что в
условии стоит именно `succeeded`, а заявки считаются через distinct.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from app.services.owner_address_stats import address_stats_for_owner

ADDRESS_A = uuid4()
ADDRESS_B = uuid4()
PROVIDER = uuid4()
NOW = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self.compiled = ""

    async def execute(self, statement):
        self.compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        return _Result(self._rows)


def _run(db: _FakeDB):
    return asyncio.run(address_stats_for_owner(db=db, provider_id=PROVIDER))


def test_kopeks_converted_to_rubles():
    """Платежи хранятся в копейках — в витрину идут рубли."""
    stats = _run(_FakeDB([(ADDRESS_A, 3, 2, 6900000, NOW)]))
    assert stats[ADDRESS_A].revenue == Decimal("69000")


def test_address_without_payments_has_zero_revenue():
    stats = _run(_FakeDB([(ADDRESS_B, 4, 0, 0, None)]))
    item = stats[ADDRESS_B]
    assert item.revenue == Decimal("0")
    assert item.deals_paid == 0
    assert item.last_paid_at is None
    # Заявки при этом есть — адрес показывают, просто он ничего не принёс.
    assert item.applications_total == 4


def test_null_aggregates_do_not_crash():
    """SQL отдаёт NULL там, где строк не нашлось, — это не должно падать."""
    stats = _run(_FakeDB([(ADDRESS_A, None, None, None, None)]))
    assert stats[ADDRESS_A].revenue == Decimal("0")
    assert stats[ADDRESS_A].applications_total == 0


def test_result_is_keyed_by_address():
    stats = _run(_FakeDB([(ADDRESS_A, 1, 1, 100, NOW), (ADDRESS_B, 2, 0, 0, None)]))
    assert set(stats) == {ADDRESS_A, ADDRESS_B}


def test_query_counts_only_succeeded_payments():
    """В выручку не должны попадать pending, failed и возвраты."""
    db = _FakeDB([])
    _run(db)
    assert "'succeeded'" in db.compiled
    for wrong in ("'pending'", "'refunded'", "'failed'"):
        assert wrong not in db.compiled


def test_query_counts_applications_distinctly():
    """Заявка с двумя платежами не должна посчитаться дважды."""
    db = _FakeDB([])
    _run(db)
    assert "count(DISTINCT" in db.compiled or "count(distinct" in db.compiled.lower()


def test_query_is_scoped_to_provider():
    """Чужие адреса в выдачу попасть не должны."""
    db = _FakeDB([])
    _run(db)
    # В скомпилированном SQL UUID печатается без дефисов.
    assert PROVIDER.hex in db.compiled
    assert "applications.provider_id" in db.compiled
