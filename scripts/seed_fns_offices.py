"""Стартовый сид справочника fns_offices + бэкфилл addresses.fns_office_id.

Демо-каталог — Москва. Скрипт по фактическим fns_number существующих адресов
создаёт московские записи fns_offices (код 77NN) и проставляет адресам
fns_office_id. Идемпотентен.

Запуск: .venv/bin/python -m scripts.seed_fns_offices
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.address import Address
from app.models.fns_office import FnsOffice

MOSCOW_REGION = "Москва"
MOSCOW_CITY = "Москва"


async def _seed() -> None:
    async with AsyncSessionLocal() as db:
        # Уникальные номера ИФНС из реальных адресов.
        numbers = sorted(
            {
                n
                for (n,) in (
                    await db.execute(
                        select(Address.fns_number).where(
                            Address.fns_number.is_not(None)
                        )
                    )
                ).all()
            }
        )
        created = 0
        linked = 0
        for number in numbers:
            code = f"77{number:02d}"
            office = (
                await db.execute(
                    select(FnsOffice).where(FnsOffice.code == code)
                )
            ).scalar_one_or_none()
            if office is None:
                office = FnsOffice(
                    code=code,
                    name=f"ИФНС России № {number} по г. Москве",
                    short_number=number,
                    region=MOSCOW_REGION,
                    city=MOSCOW_CITY,
                )
                db.add(office)
                await db.flush()
                created += 1
            # Привязываем все адреса с этим номером, у кого ещё нет office_id.
            result = await db.execute(
                update(Address)
                .where(
                    Address.fns_number == number,
                    Address.fns_office_id.is_(None),
                )
                .values(fns_office_id=office.id)
            )
            linked += result.rowcount or 0
        await db.commit()
        print(
            f"fns_offices: создано {created}, "
            f"адресов привязано {linked}, всего номеров {len(numbers)}"
        )


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
