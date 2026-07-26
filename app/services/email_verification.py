"""Подтверждение адреса электронной почты.

Публичная форма заявки заводит аккаунт на любой введённый адрес. Последствия:
опечатка — человек теряет доступ и не получает уведомлений; чужой адрес —
занимает учётку его владельца и шлёт ему письма от нашего имени.

Схема обычная: при регистрации выдаётся одноразовый токен, ссылка уходит
письмом, переход по ссылке проставляет отметку. В базе лежит только хеш
токена — утечка дампа не даёт возможности подтвердить чужой адрес.

Вход НЕ блокируется. Публичная форма создаёт заявку и аккаунт одним действием,
и запертый сразу после отправки клиент — потерянная заявка. Вместо этого в
кабинете висит напоминание, а подтверждение требуется там, где цена ошибки
реальна.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.config import settings
from app.models.user import User
from app.services.auth_security import hash_token
from app.services.email_outbox import send_email

logger = logging.getLogger(__name__)

#: Сколько живёт ссылка подтверждения.
TOKEN_TTL = timedelta(hours=48)

#: Не чаще одного письма в этот интервал — защита от «долби кнопку отправки»
#: и от использования сервиса как рассылочной пушки по чужим адресам.
RESEND_COOLDOWN = timedelta(minutes=2)

_TOKEN_BYTES = 32


def verification_path(token: str) -> str:
    return f"/verify/{token}"


def _verification_url(token: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}{verification_path(token)}"


def _message(user: User, token: str) -> tuple[str, str]:
    url = _verification_url(token)
    subject = "Подтвердите e-mail на uradres.net"
    body = (
        f"{user.full_name}, здравствуйте!\n\n"
        "Кто-то указал этот адрес при регистрации на uradres.net. "
        "Чтобы подтвердить, что он ваш, перейдите по ссылке:\n\n"
        f"{url}\n\n"
        f"Ссылка действует {int(TOKEN_TTL.total_seconds() // 3600)} часов.\n\n"
        "Если вы не регистрировались — просто проигнорируйте письмо, "
        "без подтверждения адрес не будет использоваться для уведомлений."
    )
    return subject, body


def can_resend(user: User) -> bool:
    """Прошёл ли период ожидания с прошлой отправки."""
    if user.email_verification_sent_at is None:
        return True
    return utcnow() - user.email_verification_sent_at >= RESEND_COOLDOWN


async def issue_verification(db: AsyncSession, user: User, *, send: bool = True) -> str | None:
    """Выдаёт новый токен и отправляет письмо. None — уже подтверждён.

    Токен возвращается вызывающему только для тестов и логов разработки; в
    обычной работе он уходит исключительно письмом.
    """
    if user.email_verified_at is not None:
        return None

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    user.email_verification_token_hash = hash_token(token)
    user.email_verification_sent_at = utcnow()
    await db.flush()

    if send:
        subject, body = _message(user, token)
        # send_email сам не поднимает исключений: недоступный SMTP не должен
        # ронять регистрацию — заявка важнее письма, ссылку можно перезапросить.
        await send_email(to=user.email, subject=subject, body=body)
        logger.info("email verification sent to user=%s", user.id)

    return token


class VerificationResult:
    """Итог подтверждения — чтобы отличать «уже подтверждён» от ошибки."""

    def __init__(self, *, ok: bool, already: bool = False, reason: str = "") -> None:
        self.ok = ok
        self.already = already
        self.reason = reason


async def confirm_verification(db: AsyncSession, token: str) -> VerificationResult:
    if not token or not token.strip():
        return VerificationResult(ok=False, reason="Ссылка повреждена")

    token_hash = hash_token(token.strip())
    user = (
        await db.execute(select(User).where(User.email_verification_token_hash == token_hash))
    ).scalar_one_or_none()

    if user is None:
        # Токен уже использован (хеш стёрт) либо подделан — ответ одинаковый,
        # чтобы по нему нельзя было различить эти случаи.
        return VerificationResult(
            ok=False, reason="Ссылка недействительна или уже использована"
        )

    if user.email_verified_at is not None:
        user.email_verification_token_hash = None
        await db.flush()
        return VerificationResult(ok=True, already=True)

    sent_at = user.email_verification_sent_at
    if sent_at is None or utcnow() - sent_at > TOKEN_TTL:
        return VerificationResult(
            ok=False, reason="Срок действия ссылки истёк — запросите новую"
        )

    user.email_verified_at = utcnow()
    user.email_verification_token_hash = None
    await db.flush()
    logger.info("email verified for user=%s", user.id)
    return VerificationResult(ok=True)
