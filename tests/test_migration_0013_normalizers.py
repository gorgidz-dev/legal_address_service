"""Smoke-tests for the inline normaliser helpers in migration 0013.

The migration intentionally re-implements normalisers (no app import) so
replaying old migrations doesn't depend on current app code. These tests
ensure the duplicated logic agrees with app.contacts in spirit, and that
the migration's tolerant-of-bad-data behaviour returns None on garbage
instead of raising.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "2026_05_12_0600_0013_normalize_existing_contacts.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_0013", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


def test_norm_phone_handles_russian_formats() -> None:
    assert migration._norm_phone("+7 (916) 123-45-67") == "+79161234567"
    assert migration._norm_phone("8 916 123-45-67") == "+79161234567"
    assert migration._norm_phone("9161234567") == "+79161234567"
    assert migration._norm_phone("+1-415-555-1234") == "+14155551234"


def test_norm_phone_returns_none_on_garbage_or_empty() -> None:
    assert migration._norm_phone(None) is None
    assert migration._norm_phone("") is None
    assert migration._norm_phone("   ") is None
    assert migration._norm_phone("abc") is None
    assert migration._norm_phone("12345") is None  # too short
    assert migration._norm_phone("+0123456789") is None  # leading 0 after + is invalid E.164


def test_norm_email_lowercases_and_validates() -> None:
    assert migration._norm_email("USER@EXAMPLE.COM") == "user@example.com"
    assert migration._norm_email("  user@example.com  ") == "user@example.com"
    assert migration._norm_email("bad") is None
    assert migration._norm_email("a@b") is None  # TLD too short


def test_norm_name_trims_and_collapses_whitespace() -> None:
    assert migration._norm_name("  Ольга   Туманова  ") == "Ольга Туманова"
    assert migration._norm_name("Хо") == "Хо"
    assert migration._norm_name(None) is None
    assert migration._norm_name("") is None
    assert migration._norm_name("X") is None  # too short
