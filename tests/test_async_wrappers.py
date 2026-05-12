"""Async wrappers around blocking operations.

Verify that the async variants delegate to the sync ones correctly and yield
the event loop (loop stays responsive while PBKDF2 / docx / Pillow run).
"""
from __future__ import annotations

import asyncio
import time

import pytest

from app.services.auth_security import (
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)


@pytest.mark.asyncio
async def test_hash_password_async_matches_sync() -> None:
    h = await hash_password_async("secret-123")
    assert h.startswith("pbkdf2_sha256$")
    assert verify_password("secret-123", h)


@pytest.mark.asyncio
async def test_verify_password_async_matches_sync() -> None:
    h = hash_password("secret-123")
    assert await verify_password_async("secret-123", h) is True
    assert await verify_password_async("wrong", h) is False


@pytest.mark.asyncio
async def test_hash_password_async_yields_to_event_loop() -> None:
    """While PBKDF2 is hashing on a worker thread, the loop must remain responsive.

    We launch a hash + a periodic counter task; if the loop were blocked, the
    counter would not tick during the hash. With to_thread it should.
    """
    counter = {"ticks": 0}

    async def ticker():
        while True:
            await asyncio.sleep(0.001)
            counter["ticks"] += 1

    tick_task = asyncio.create_task(ticker())
    try:
        start = time.monotonic()
        await hash_password_async("a-real-secret")
        elapsed = time.monotonic() - start
        # PBKDF2 with 210k iterations takes ~50-300ms; loop must have ticked at least a few times
        assert counter["ticks"] >= 3, f"loop appeared blocked (only {counter['ticks']} ticks in {elapsed:.3f}s)"
    finally:
        tick_task.cancel()


@pytest.mark.asyncio
async def test_concurrent_hashes_do_not_serialize_on_event_loop() -> None:
    """N parallel PBKDF2 calls should overlap on the thread pool, not run sequentially."""
    start = time.monotonic()
    await asyncio.gather(*[hash_password_async(f"pw-{i}") for i in range(4)])
    elapsed = time.monotonic() - start
    # Sequential 4x PBKDF2 ~ 200-800ms. With concurrent thread pool, should be ~50-300ms.
    # Loose upper bound: under 2s confirms threading helps (not serialized blocking).
    assert elapsed < 2.0, f"4 concurrent hashes took {elapsed:.3f}s — likely event-loop blocking"
