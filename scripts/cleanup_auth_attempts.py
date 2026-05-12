"""CLI: удаление старых записей из auth_attempts.

Запуск (cron/systemd-timer, например, раз в час):

    source .venv/bin/activate
    python -m scripts.cleanup_auth_attempts

Опции:

    --hours N    Удалить записи старше N часов (по умолчанию 24).

Таблица auth_attempts растёт линейно с количеством попыток входа и сабмитов
публичных форм. После прохождения окна rate-limit (15 мин для логина, 1 ч
для публичных форм) записи бесполезны. Этот скрипт держит таблицу компактной.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from app.database import AsyncSessionLocal
from app.services.auth_attempts_cleanup import cleanup_auth_attempts


async def _run(retention: timedelta) -> int:
    async with AsyncSessionLocal() as db:
        deleted = await cleanup_auth_attempts(db, retention)
        await db.commit()
        return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup auth_attempts table")
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Удалить записи старше N часов (по умолчанию 24)",
    )
    args = parser.parse_args()
    deleted = asyncio.run(_run(timedelta(hours=args.hours)))
    print(f"Удалено записей: {deleted}")


if __name__ == "__main__":
    main()
