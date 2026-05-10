from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from app.database import AsyncSessionLocal
from app.services.marketplace_seed import DEMO_PASSWORD, marketplace_demo_payload, seed_marketplace_demo


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        return super().default(obj)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Создать или показать демо-данные маркетплейса юридических адресов.")
    parser.add_argument(
        "--print-json",
        action="store_true",
        help="Не писать в БД, а вывести payload демо-данных.",
    )
    parser.add_argument(
        "--password",
        default=DEMO_PASSWORD,
        help="Пароль для демо-аккаунтов. По умолчанию demo12345.",
    )
    return parser


async def _seed(password: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await seed_marketplace_demo(db=db, password=password)
        await db.commit()
    print(json.dumps(result, ensure_ascii=False, indent=2, cls=_Encoder))


def main() -> None:
    args = _parser().parse_args()
    if not args.print_json:
        asyncio.run(_seed(args.password))
        return
    payload = marketplace_demo_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2, cls=_Encoder))


if __name__ == "__main__":
    main()
