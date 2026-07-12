from __future__ import annotations

import pytest

from app.services.auth_security import dummy_verify
from app.services.webhooks import UnsafeWebhookUrl, assert_safe_webhook_url


# ------------------- SSRF-фильтр webhook-URL -------------------
# Литеральные IP не требуют DNS → тесты офлайновые и детерминированные.


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/hook",
        "http://localhost/hook",
        "https://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
        "http://10.0.0.5/hook",
        "http://192.168.1.10/hook",
        "http://172.16.0.1/hook",
        "http://[::1]/hook",  # IPv6 loopback
        "http://0.0.0.0/hook",  # unspecified
    ],
)
def test_rejects_internal_targets(url: str) -> None:
    with pytest.raises(UnsafeWebhookUrl):
        assert_safe_webhook_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/hook",
        "file:///etc/passwd",
        "gopher://127.0.0.1/",
        "notaurl",
    ],
)
def test_rejects_non_http_or_hostless(url: str) -> None:
    with pytest.raises(UnsafeWebhookUrl):
        assert_safe_webhook_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://8.8.8.8/hook",  # публичный IP-литерал — без DNS
        "http://93.184.216.34/hook",
    ],
)
def test_allows_public_targets(url: str) -> None:
    assert assert_safe_webhook_url(url) is None


# ------------------- Тайминг логина (user-enumeration) -------------------


def test_dummy_verify_runs_and_returns_none() -> None:
    # Прогоняет PBKDF2 впустую; должен отработать без исключений.
    assert dummy_verify("любой-пароль") is None
