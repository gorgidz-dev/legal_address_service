"""Verify DB engine picks up pool settings from config."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.database import _build_engine_kwargs


def test_engine_kwargs_use_configured_pool(monkeypatch) -> None:
    from app.config import settings as global_settings

    monkeypatch.setattr(global_settings, "db_pool_size", 7)
    monkeypatch.setattr(global_settings, "db_max_overflow", 14)
    monkeypatch.setattr(global_settings, "db_pool_timeout", 17)
    monkeypatch.setattr(global_settings, "db_pool_recycle", 999)
    monkeypatch.setattr(global_settings, "db_pool_pre_ping", False)
    monkeypatch.setattr(global_settings, "db_echo", True)

    kwargs = _build_engine_kwargs()
    assert kwargs["pool_size"] == 7
    assert kwargs["max_overflow"] == 14
    assert kwargs["pool_timeout"] == 17
    assert kwargs["pool_recycle"] == 999
    assert kwargs["pool_pre_ping"] is False
    assert kwargs["echo"] is True


def test_engine_kwargs_skips_pool_for_sqlite(monkeypatch) -> None:
    from app.config import settings as global_settings

    monkeypatch.setattr(global_settings, "database_url", "sqlite+aiosqlite:///:memory:")
    kwargs = _build_engine_kwargs()
    assert "pool_size" not in kwargs
    assert "max_overflow" not in kwargs


def test_engine_actually_constructs_with_pool() -> None:
    """End-to-end: engine builds with configured pool params (using a fake URL)."""
    cfg = Settings(
        database_url="postgresql+asyncpg://u:p@localhost:5432/x",
        db_pool_size=4,
        db_max_overflow=8,
        db_pool_timeout=20,
        db_pool_recycle=600,
        db_pool_pre_ping=True,
    )
    eng = create_async_engine(
        cfg.database_url,
        echo=False,
        future=True,
        pool_size=cfg.db_pool_size,
        max_overflow=cfg.db_max_overflow,
        pool_timeout=cfg.db_pool_timeout,
        pool_recycle=cfg.db_pool_recycle,
        pool_pre_ping=cfg.db_pool_pre_ping,
    )
    pool = eng.pool
    assert pool.size() == 4
    assert pool._max_overflow == 8
    assert pool._timeout == 20
    assert pool._recycle == 600


def test_default_pool_values_are_sane() -> None:
    cfg = Settings()
    assert cfg.db_pool_size >= 5
    assert cfg.db_max_overflow >= 0
    assert cfg.db_pool_timeout >= 5
    assert cfg.db_pool_recycle >= 60
    assert cfg.db_pool_pre_ping is True
