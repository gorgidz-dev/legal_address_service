"""Async SQLAlchemy engine + сессия + FastAPI-зависимость."""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _build_engine_kwargs() -> dict:
    """Pool config applies to PG; SQLite/in-memory engines ignore it (NullPool)."""
    if settings.database_url.startswith("sqlite"):
        return {"echo": settings.db_echo, "future": True}
    return {
        "echo": settings.db_echo,
        "future": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": settings.db_pool_pre_ping,
    }


engine = create_async_engine(settings.database_url, **_build_engine_kwargs())

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Открывает сессию на запрос; rollback при ошибке, close при выходе."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
