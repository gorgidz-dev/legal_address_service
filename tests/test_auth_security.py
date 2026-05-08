from __future__ import annotations

from app.services.auth_security import hash_password, hash_token, verify_password


def test_password_hash_roundtrip_and_wrong_password_rejected() -> None:
    password_hash = hash_password("strong-password-2026")

    assert password_hash.startswith("pbkdf2_sha256$")
    assert verify_password("strong-password-2026", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_password_hash_uses_salt() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_token_hash_is_stable_and_not_plain_token() -> None:
    token = "session-token-value"

    assert hash_token(token) == hash_token(token)
    assert hash_token(token) != token
