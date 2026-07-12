from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os


PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 210_000


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        algorithm, iterations_value, salt_value, digest_value = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_value)
        salt = _b64decode(salt_value)
        expected_digest = _b64decode(digest_value)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


async def hash_password_async(password: str) -> str:
    """PBKDF2 is CPU-bound — run on the default executor so the event loop stays free."""
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str | None) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)


# Фиктивный хэш для выравнивания времени ответа, когда аккаунта нет (или он
# отключён): без него verify_password не вызывается и «нет пользователя»
# отвечает заметно быстрее «неверный пароль» → user-enumeration по таймингу.
_DUMMY_PASSWORD_HASH = hash_password("uradres-timing-equalizer")


def dummy_verify(password: str) -> None:
    """Прогоняет PBKDF2 впустую — чтобы неуспешный логин занимал столько же,
    сколько проверка реального пароля, независимо от наличия пользователя."""
    verify_password(password, _DUMMY_PASSWORD_HASH)


async def dummy_verify_async(password: str) -> None:
    await asyncio.to_thread(dummy_verify, password)
