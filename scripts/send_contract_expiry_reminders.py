"""Ежедневный CLI: рассылка напоминаний клиентам об истекающих договорах.

Запуск (вручную или из cron/systemd-timer):

    source .venv/bin/activate
    python -m scripts.send_contract_expiry_reminders

Опции:

    --today YYYY-MM-DD          Переопределить «сегодня» (для отладки/бэкфилла).
    --milestones 30,7,1         Список интервалов в днях (по умолчанию 30,7,1).

Идемпотентность: для одной пары (договор, milestone) событие создаётся ровно один раз,
повторный запуск в тот же день ничего не дублирует.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import date

from app.database import AsyncSessionLocal
from app.services.contract_expiry_reminders import (
    DEFAULT_MILESTONES_DAYS,
    send_contract_expiry_reminders,
)


async def _run(today: date, milestones: tuple[int, ...]) -> int:
    async with AsyncSessionLocal() as db:
        sent = await send_contract_expiry_reminders(
            db=db,
            today=today,
            milestones_days=milestones,
        )
        if sent:
            await db.commit()
        return len(sent)


def _parse_milestones(value: str) -> tuple[int, ...]:
    parts = [chunk.strip() for chunk in value.split(",") if chunk.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("Список milestones не может быть пустым")
    try:
        return tuple(int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Каждый milestone должен быть целым: {exc}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Напоминания об истекающих договорах")
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
        help="Список интервалов в днях, через запятую (по умолчанию 30,7,1)",
    )
    args = parser.parse_args()

    count = asyncio.run(_run(today=args.today, milestones=args.milestones))
    print(f"Отправлено напоминаний: {count}")


if __name__ == "__main__":
    main()
