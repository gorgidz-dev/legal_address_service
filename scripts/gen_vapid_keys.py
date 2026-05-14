"""Сгенерировать пару VAPID-ключей для Web Push.

Запуск:
    .venv/bin/python -m scripts.gen_vapid_keys

Вывод печатает значения для .env (VAPID_PUBLIC_KEY и VAPID_PRIVATE_PEM).
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def main() -> None:
    v = Vapid01()
    v.generate_keys()
    nums = v.public_key.public_numbers()
    x = nums.x.to_bytes(32, "big")
    y = nums.y.to_bytes(32, "big")
    raw_pub = b"\x04" + x + y
    pub_b64 = base64.urlsafe_b64encode(raw_pub).decode().rstrip("=")
    priv_pem = v.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    print("VAPID_PUBLIC_KEY=" + pub_b64)
    print("VAPID_PRIVATE_PEM<<EOF")
    print(priv_pem.rstrip())
    print("EOF")


if __name__ == "__main__":
    main()
