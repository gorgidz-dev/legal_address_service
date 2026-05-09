from __future__ import annotations

import json
from decimal import Decimal

from app.services.marketplace_seed import marketplace_demo_payload


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def main() -> None:
    payload = marketplace_demo_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2, cls=_Encoder))


if __name__ == "__main__":
    main()
