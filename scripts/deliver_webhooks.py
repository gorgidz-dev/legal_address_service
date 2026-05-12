"""CLI: воркер доставки webhook'ов.

Запуск (cron каждую минуту):

    source .venv/bin/activate
    python -m scripts.deliver_webhooks

Опции:

    --limit N    Сколько доставок забирать за раз (по умолчанию 50).

Логика:
- Берёт N pending-доставок с scheduled_for <= now()
- Атомарно помечает их in_progress (защита от двойной обработки)
- POST с HMAC-подписью
- На успех -> sent. На ошибку -> backoff и pending снова, либо dead после MAX_ATTEMPTS.
"""
from __future__ import annotations

import argparse
import asyncio

from app.database import AsyncSessionLocal
from app.services.webhooks import deliver_pending


async def _run(limit: int) -> int:
    async with AsyncSessionLocal() as db:
        results = await deliver_pending(db, limit=limit)
        return len(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deliver pending webhooks")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Максимум доставок за запуск (по умолчанию 50)",
    )
    args = parser.parse_args()
    processed = asyncio.run(_run(args.limit))
    print(f"Обработано доставок: {processed}")


if __name__ == "__main__":
    main()
