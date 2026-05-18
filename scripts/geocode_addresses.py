"""Бэкфилл координат адресов через DaData (geo_lat/geo_lon).

Берёт все адреса с пустыми latitude/longitude, геокодит full_address и
сохраняет точку. Идемпотентен — уже геокодированные пропускает.

Требует DADATA_TOKEN в .env. Без токена скрипт ничего не делает.

Запуск: .venv/bin/python -m scripts.geocode_addresses
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.address import Address
from app.services.dadata_address import geocode


async def _run() -> None:
    if not settings.dadata_token:
        print("DADATA_TOKEN не задан — геокодинг пропущен")
        return

    async with AsyncSessionLocal() as db:
        addresses = list(
            (
                await db.execute(
                    select(Address).where(Address.latitude.is_(None))
                )
            ).scalars()
        )
        if not addresses:
            print("Все адреса уже геокодированы")
            return

        ok = 0
        failed = 0
        for address in addresses:
            point = await geocode(address.full_address)
            if point is None:
                failed += 1
                print(f"[skip] {address.full_address}: точка не найдена")
                continue
            lat, lon = point
            address.latitude = Decimal(str(round(lat, 6)))
            address.longitude = Decimal(str(round(lon, 6)))
            ok += 1
            print(f"[ok]   {address.full_address}: {lat:.5f}, {lon:.5f}")

        await db.commit()
        print(f"Done: геокодировано {ok}, не найдено {failed}")


if __name__ == "__main__":
    asyncio.run(_run())
