"""Ежедневный CLI: напоминания по внутренним срокам этапов заявки.

Собственнику — «пора отработать заявку», оператору — «собственник тянет».
Клиенту не адресуется ничего: сроки внутренние.

Запуск (вручную или из cron/systemd-timer, рядом с send_contract_expiry_reminders):

    source .venv/bin/activate
    python -m scripts.send_stage_deadline_reminders

Опции:

    --now 2026-07-30T12:00:00+00:00   Переопределить «сейчас» (отладка, бэкфилл).

Идемпотентность: на одну пару (срок, веха) событие создаётся ровно один раз.
Смена статуса меняет срок, и по новому сроку напоминания идут заново — это
намеренно: этап другой, отсчёт другой.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.services.sla_reminders import send_stage_deadline_reminders


async def _run(now: datetime) -> int:
    async with AsyncSessionLocal() as db:
        sent = await send_stage_deadline_reminders(db=db, now=now)
        if sent:
            await db.commit()
        return len(sent)


def _parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    # Наивная дата означала бы «в неизвестной зоне», а сроки считаются в UTC.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Напоминания по внутренним срокам этапов заявки"
    )
    parser.add_argument(
        "--now",
        type=_parse_now,
        default=datetime.now(timezone.utc),
        help="Переопределить момент «сейчас» в формате ISO-8601",
    )
    args = parser.parse_args()

    count = asyncio.run(_run(now=args.now))
    print(f"Создано напоминаний: {count}")


if __name__ == "__main__":
    main()
