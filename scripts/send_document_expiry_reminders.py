"""Ежедневный CLI: напоминания собственникам об истекающих документах адреса.

Запуск (из cron, рядом с двумя другими рассылками):

    python -m scripts.send_document_expiry_reminders

Опции:

    --today YYYY-MM-DD          Переопределить «сегодня» (отладка, бэкфилл).
    --milestones 30,7,1,0       Вехи в днях до истечения (по умолчанию 30,7,1,0).

Идемпотентность: на пару (документ, веха) уведомление создаётся один раз.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date

from app.database import AsyncSessionLocal
from app.services.document_expiry_reminders import (
    DEFAULT_MILESTONES_DAYS,
    send_document_expiry_reminders,
)


async def _run(today: date, milestones: tuple[int, ...]) -> int:
    async with AsyncSessionLocal() as db:
        sent = await send_document_expiry_reminders(
            db=db, today=today, milestones_days=milestones
        )
        if sent:
            await db.commit()
        return len(sent)


def _parse_milestones(value: str) -> tuple[int, ...]:
    parts = [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("Список вех не может быть пустым")
    try:
        return tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Каждая веха — целое число: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Напоминания об истекающих документах адреса"
    )
    parser.add_argument(
        "--today",
        type=lambda v: date.fromisoformat(v),
        default=date.today(),
        help="Переопределить дату «сегодня» в формате YYYY-MM-DD",
    )
    parser.add_argument(
        "--milestones",
        type=_parse_milestones,
        default=DEFAULT_MILESTONES_DAYS,
        help="Вехи в днях до истечения, через запятую (по умолчанию 30,7,1,0)",
    )
    args = parser.parse_args()

    count = asyncio.run(_run(today=args.today, milestones=args.milestones))
    print(f"Создано уведомлений: {count}")


if __name__ == "__main__":
    main()
