"""Тесты отправки почты: стаб без SMTP, реальная отправка с моком smtplib."""
from __future__ import annotations

import logging

import pytest

from app import config as config_module
from app.services import email_outbox


@pytest.mark.asyncio
async def test_stub_logs_when_no_smtp_host(monkeypatch, caplog) -> None:
    monkeypatch.setattr(config_module.settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(email_outbox.settings, "smtp_host", "", raising=False)
    with caplog.at_level(logging.INFO, logger="email_outbox"):
        await email_outbox.send_email(
            to="user@example.com", subject="Тест", body="тело"
        )
    assert any("email-stub" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_sends_via_smtp_starttls(monkeypatch) -> None:
    s = email_outbox.settings
    monkeypatch.setattr(s, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(s, "smtp_port", 587, raising=False)
    monkeypatch.setattr(s, "smtp_username", "noreply@uradres.market", raising=False)
    monkeypatch.setattr(s, "smtp_password", "secret", raising=False)
    monkeypatch.setattr(s, "smtp_from", "Uradres <noreply@uradres.market>", raising=False)
    monkeypatch.setattr(s, "smtp_use_tls", True, raising=False)
    monkeypatch.setattr(s, "smtp_use_ssl", False, raising=False)

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["from"] = msg["From"]
            sent["subject"] = msg["Subject"]

    monkeypatch.setattr(email_outbox.smtplib, "SMTP", FakeSMTP)

    await email_outbox.send_email(
        to="client@example.com", subject="Отзыв одобрен", body="Текст письма"
    )

    assert sent["host"] == "smtp.example.com"
    assert sent["port"] == 587
    assert sent["starttls"] is True
    assert sent["login"] == ("noreply@uradres.market", "secret")
    assert sent["to"] == "client@example.com"
    assert sent["subject"] == "Отзыв одобрен"
    assert "noreply@uradres.market" in sent["from"]


@pytest.mark.asyncio
async def test_send_failure_is_swallowed(monkeypatch, caplog) -> None:
    """Сбой SMTP не должен пробрасываться (не ронять основной запрос)."""
    monkeypatch.setattr(email_outbox.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_outbox.settings, "smtp_use_ssl", False, raising=False)
    monkeypatch.setattr(email_outbox.settings, "smtp_use_tls", False, raising=False)

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(email_outbox, "_send_sync", boom)

    with caplog.at_level(logging.ERROR, logger="email_outbox"):
        # не должно бросить исключение
        await email_outbox.send_email(to="x@example.com", subject="s", body="b")
    assert any("email send failed" in r.message for r in caplog.records)
