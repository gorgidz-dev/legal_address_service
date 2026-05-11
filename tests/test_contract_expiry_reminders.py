from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.enums import ApplicationEventKind, NotificationAudience
from app.models.application_event import ApplicationEvent
from app.models.contract import Contract
from app.services.contract_expiry_reminders import (
    DEFAULT_MILESTONES_DAYS,
    send_contract_expiry_reminders,
)


def _make_contract(*, end_date: date, application_id: UUID | None = None) -> Contract:
    return Contract(
        id=uuid4(),
        application_id=application_id or uuid4(),
        number=f"ДА-2026-{uuid4().hex[:4]}",
        contract_date=end_date - timedelta(days=180),
        start_date=end_date - timedelta(days=180),
        end_date=end_date,
        price_total=Decimal("25000"),
        price_total_in_words="двадцать пять тысяч",
    )


class _FakeScalars:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def all(self) -> list[Any]:
        return list(self._items)


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)

    def all(self) -> list[Any]:
        # эмулируем возврат payload-кортежей при select(ApplicationEvent.payload)
        return [(item,) if not isinstance(item, tuple) else item for item in self._rows]


class _FakeDB:
    """Эмулирует достаточный кусок AsyncSession для send_contract_expiry_reminders.

    Логика выбора результата по форме statement: если в statement упоминается Contract —
    отдаём список договоров, фильтруя по end_date == target_end_date; если упоминается
    ApplicationEvent.payload — отдаём существующие payload-ы reminder'ов.
    """

    def __init__(self, contracts: list[Contract], existing_events: list[ApplicationEvent] | None = None) -> None:
        self._contracts = contracts
        self.added: list[ApplicationEvent] = list(existing_events or [])

    async def execute(self, statement):
        compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
        if "FROM contracts" in compiled:
            target = self._extract_target_end_date(compiled)
            matching = [c for c in self._contracts if c.end_date == target]
            return _FakeResult(matching)
        if "FROM application_events" in compiled:
            target_app_id = self._extract_application_id(compiled)
            payloads = [
                e.payload
                for e in self.added
                if isinstance(e, ApplicationEvent)
                and UUID(str(e.application_id)) == target_app_id
                and e.kind == ApplicationEventKind.CONTRACT_EXPIRING.value
            ]
            return _FakeResult(payloads)
        raise AssertionError(f"Неожиданный statement: {compiled!r}")

    def add(self, item: Any) -> None:
        if isinstance(item, ApplicationEvent) and item.id is None:
            item.id = uuid4()
        self.added.append(item)

    @staticmethod
    def _extract_target_end_date(compiled: str) -> date:
        # ищем вид "end_date = '2026-06-10'"
        marker = "end_date = "
        idx = compiled.find(marker)
        assert idx >= 0, compiled
        quoted = compiled[idx + len(marker):]
        start = quoted.find("'") + 1
        end = quoted.find("'", start)
        return date.fromisoformat(quoted[start:end])

    @staticmethod
    def _extract_application_id(compiled: str) -> UUID:
        marker = "application_id = "
        idx = compiled.find(marker)
        assert idx >= 0, compiled
        quoted = compiled[idx + len(marker):]
        start = quoted.find("'") + 1
        end = quoted.find("'", start)
        return UUID(quoted[start:end])


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_default_milestones_are_30_7_and_1() -> None:
    assert DEFAULT_MILESTONES_DAYS == (30, 7, 1)


def test_creates_event_for_each_milestone_match() -> None:
    today = date(2026, 5, 11)
    contracts = [
        _make_contract(end_date=today + timedelta(days=30)),
        _make_contract(end_date=today + timedelta(days=7)),
        _make_contract(end_date=today + timedelta(days=1)),
        _make_contract(end_date=today + timedelta(days=15)),  # вне окон
    ]
    db = _FakeDB(contracts=contracts)
    sent = _run(send_contract_expiry_reminders(db=db, today=today))

    assert len(sent) == 3
    milestones = sorted(item.milestone_days for item in sent)
    assert milestones == [1, 7, 30]
    events = [item for item in db.added if isinstance(item, ApplicationEvent)]
    assert len(events) == 3
    for event in events:
        assert event.kind == ApplicationEventKind.CONTRACT_EXPIRING.value
        assert event.audience == NotificationAudience.CLIENT.value
        assert event.payload["contract_id"]
        assert event.payload["milestone_days"] in (1, 7, 30)


def test_is_idempotent_for_same_milestone() -> None:
    today = date(2026, 5, 11)
    contract = _make_contract(end_date=today + timedelta(days=7))
    existing = ApplicationEvent(
        id=uuid4(),
        application_id=contract.application_id,
        kind=ApplicationEventKind.CONTRACT_EXPIRING.value,
        audience=NotificationAudience.CLIENT.value,
        title="...",
        message="...",
        payload={"milestone_days": 7, "contract_id": str(contract.id)},
        created_at=None,  # type: ignore[arg-type]
    )
    db = _FakeDB(contracts=[contract], existing_events=[existing])

    sent = _run(send_contract_expiry_reminders(db=db, today=today))

    assert sent == []
    new_events = [
        e for e in db.added
        if isinstance(e, ApplicationEvent) and e.id != existing.id
    ]
    assert new_events == []


def test_skips_milestones_with_no_matching_contracts() -> None:
    today = date(2026, 5, 11)
    db = _FakeDB(contracts=[_make_contract(end_date=today + timedelta(days=100))])
    sent = _run(send_contract_expiry_reminders(db=db, today=today))
    assert sent == []
    assert not [e for e in db.added if isinstance(e, ApplicationEvent)]


def test_custom_milestones_override_defaults() -> None:
    today = date(2026, 5, 11)
    contract = _make_contract(end_date=today + timedelta(days=14))
    db = _FakeDB(contracts=[contract])
    sent = _run(
        send_contract_expiry_reminders(
            db=db, today=today, milestones_days=(14,)
        )
    )
    assert len(sent) == 1
    assert sent[0].milestone_days == 14
