"""Проверка production-валидатора в Settings.

См. docs/security-checklist.md — какие переменные нужны в проде и почему.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def _make_settings(**overrides):
    """Pydantic-Settings обычно читает env, поэтому подменяем через kwargs."""
    base = {
        "app_env": "production",
        "session_cookie_secure": True,
        "payment_webhook_secret": "x" * 32,
        "dadata_token": "tok",
        "dadata_secret": "sec",
        "storage_backend": "s3",
        "vapid_subject": "mailto:ops@example.com",
        "db_echo": False,
    }
    base.update(overrides)
    return Settings(**base)


def test_production_with_all_required_passes():
    settings = _make_settings()
    assert settings.app_env == "production"


def test_production_rejects_default_session_cookie_secure():
    with pytest.raises(ValidationError) as e:
        _make_settings(session_cookie_secure=False)
    assert "SESSION_COOKIE_SECURE" in str(e.value)


def test_production_rejects_empty_webhook_secret():
    with pytest.raises(ValidationError) as e:
        _make_settings(payment_webhook_secret="")
    assert "PAYMENT_WEBHOOK_SECRET" in str(e.value)


def test_production_rejects_default_vapid_subject():
    with pytest.raises(ValidationError) as e:
        _make_settings(vapid_subject="mailto:noreply@uradres.example")
    assert "VAPID_SUBJECT" in str(e.value)


def test_production_rejects_local_storage():
    with pytest.raises(ValidationError) as e:
        _make_settings(storage_backend="local")
    assert "STORAGE_BACKEND=local" in str(e.value)


def test_production_rejects_db_echo():
    with pytest.raises(ValidationError) as e:
        _make_settings(db_echo=True)
    assert "DB_ECHO" in str(e.value)


def test_development_is_lax():
    # дефолты не должны падать в development
    s = Settings(
        app_env="development",
        session_cookie_secure=False,
        payment_webhook_secret="",
        storage_backend="local",
    )
    assert s.app_env == "development"
