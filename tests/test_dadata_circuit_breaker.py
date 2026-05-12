from __future__ import annotations

import time

import pytest

from app.services.dadata import (
    CircuitBreaker,
    DaDataError,
    DaDataService,
)


def test_breaker_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=0.5)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_breaker_opens_after_threshold_consecutive_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False


def test_breaker_success_resets_failure_count() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10.0)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    # 1 failure after success → not open
    assert cb.state == "closed"


def test_breaker_transitions_to_half_open_after_recovery() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    time.sleep(0.06)
    assert cb.state == "half_open"
    assert cb.allow_request() is True


def test_breaker_half_open_success_closes() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    assert cb.state == "half_open"
    cb.record_success()
    assert cb.state == "closed"


def test_breaker_half_open_failure_reopens() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.06)
    cb.record_failure()
    assert cb.state == "open"


class _FakeFailingClient:
    def __init__(self):
        self.calls = 0

    async def find_by_inn(self, inn: str):
        self.calls += 1
        raise DaDataError("network down")


class _FakeOKClient:
    def __init__(self):
        self.calls = 0

    async def find_by_inn(self, inn: str):
        self.calls += 1
        return None  # signal "not found" — doesn't matter for breaker testing


@pytest.mark.asyncio
async def test_service_fast_fails_when_breaker_open() -> None:
    service = DaDataService(
        token="x",
        breaker=CircuitBreaker(failure_threshold=2, recovery_seconds=10.0),
    )
    failing = _FakeFailingClient()
    service._client = failing  # type: ignore[assignment]

    # Two failures → breaker opens
    for _ in range(2):
        with pytest.raises(DaDataError):
            await service.lookup(f"inn-{_}")

    assert failing.calls == 2

    # Third call should NOT hit the client; breaker fast-fails.
    with pytest.raises(DaDataError, match="circuit breaker"):
        await service.lookup("any-inn")
    assert failing.calls == 2  # no extra call


@pytest.mark.asyncio
async def test_service_recovers_after_window() -> None:
    service = DaDataService(
        token="x",
        breaker=CircuitBreaker(failure_threshold=1, recovery_seconds=0.05),
    )
    failing = _FakeFailingClient()
    service._client = failing  # type: ignore[assignment]
    with pytest.raises(DaDataError):
        await service.lookup("inn-1")
    assert service._breaker.state == "open"

    time.sleep(0.06)

    # Replace client with OK one for half-open trial
    service._client = _FakeOKClient()  # type: ignore[assignment]
    result = await service.lookup("inn-2")
    assert result is None
    assert service._breaker.state == "closed"
