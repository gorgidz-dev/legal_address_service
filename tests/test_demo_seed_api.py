from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.demo import DemoCredential, DemoSeedCounts, DemoSeedRequest, DemoSeedResult


class FakeDemoSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_demo_seed_endpoint_returns_result_and_commits(monkeypatch) -> None:
    from app.routers import demo

    fake_db = FakeDemoSession()

    async def fake_seed_marketplace_demo(*, db, password: str) -> DemoSeedResult:
        assert db is fake_db
        assert password == "demo12345"
        return DemoSeedResult(
            created=DemoSeedCounts(users=1, providers=1),
            updated=DemoSeedCounts(),
            credentials=[
                DemoCredential(
                    email="admin@uradres-demo.ru",
                    full_name="Администратор площадки",
                    role="admin",
                    password="demo12345",
                )
            ],
        )

    monkeypatch.setattr(demo, "seed_marketplace_demo", fake_seed_marketplace_demo)

    result = await demo.seed_demo_data(
        payload=DemoSeedRequest(),
        db=fake_db,
        admin=SimpleNamespace(id="admin-id"),
    )

    assert fake_db.committed is True
    assert result.created.users == 1
    assert result.credentials[0].email == "admin@uradres-demo.ru"
