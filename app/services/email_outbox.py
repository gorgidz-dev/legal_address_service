"""Стаб для исходящей почты.

Реального SMTP пока нет — пишем в лог. Когда подключим провайдера (SES,
Postmark, sendgrid, etc), реализация заменит `send_email` без изменений
вызывающих мест.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("email_outbox")


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Логгер вместо реального SMTP. Замени реализацию при подключении провайдера."""
    logger.info("[email-stub] to=%s subject=%r body=%r", to, subject, body[:400])
