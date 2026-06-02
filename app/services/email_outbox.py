"""Исходящая почта.

Если SMTP настроен (settings.smtp_host задан) — реально отправляет письмо через
SMTP (stdlib smtplib в отдельном потоке, чтобы не блокировать event loop).
Если SMTP не настроен — пишет в лог (стаб), как раньше. Сбой отправки не
пробрасывается наверх: уведомление по почте не должно ронять основной запрос
(оно дублируется in-app), поэтому ошибки логируются.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.config import settings

logger = logging.getLogger("email_outbox")


def _sender() -> str:
    """Адрес отправителя: smtp_from или, если пуст, smtp_username."""
    return settings.smtp_from.strip() or settings.smtp_username.strip()


def _send_sync(to: str, subject: str, body: str) -> None:
    """Блокирующая отправка письма через smtplib. Вызывается в потоке."""
    msg = EmailMessage()
    from_name, from_addr = parseaddr(_sender())
    msg["From"] = formataddr((from_name, from_addr)) if from_name else from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.smtp_use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout,
            context=context,
        ) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=settings.smtp_timeout,
        ) as server:
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Отправляет письмо. Без SMTP — пишет в лог. Ошибки не пробрасывает."""
    if not settings.smtp_host:
        logger.info(
            "[email-stub] to=%s subject=%r body=%r", to, subject, body[:400]
        )
        return

    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
        logger.info("email sent to=%s subject=%r", to, subject)
    except Exception:  # noqa: BLE001 — почта не должна ронять основной запрос
        logger.exception("email send failed to=%s subject=%r", to, subject)
