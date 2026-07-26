"""CSRF-защита: double-submit cookie."""

from __future__ import annotations

import pytest
from fastapi import Response

from app.services.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    csrf_check_required,
    delete_csrf_cookie,
    generate_csrf_token,
    set_csrf_cookie,
    tokens_match,
)


def test_generated_tokens_are_unique_and_long() -> None:
    tokens = {generate_csrf_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS", "TRACE", "get", "head"])
def test_safe_methods_never_require_token(method: str) -> None:
    assert csrf_check_required(method=method, authenticated_by_cookie=True) is False


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "post"])
def test_unsafe_methods_require_token_for_cookie_auth(method: str) -> None:
    assert csrf_check_required(method=method, authenticated_by_cookie=True) is True


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_bearer_clients_are_exempt(method: str) -> None:
    """Браузер сам заголовок Authorization не подставляет — CSRF там невозможен.

    Если бы проверка распространялась и на Bearer, мобильное приложение
    сломалось бы, не получив ничего взамен в безопасности.
    """
    assert csrf_check_required(method=method, authenticated_by_cookie=False) is False


def test_matching_tokens_pass() -> None:
    token = generate_csrf_token()
    assert tokens_match(token, token) is True


def test_mismatched_tokens_fail() -> None:
    assert tokens_match(generate_csrf_token(), generate_csrf_token()) is False


@pytest.mark.parametrize(
    ("cookie", "header"),
    [
        (None, None),
        ("", ""),
        ("token", None),
        (None, "token"),
        ("token", ""),
        ("", "token"),
    ],
)
def test_missing_or_empty_values_never_match(cookie, header) -> None:
    """Пустое значение не должно «совпасть» с пустым — иначе защиту снимает
    обычный запрос без куки и без заголовка."""
    assert tokens_match(cookie, header) is False


@pytest.mark.parametrize(
    "header",
    ["подделка", "tökén", "日本語", "\U0001f600", "a" * 10_000],
)
def test_non_ascii_header_is_rejected_not_crashed(header: str) -> None:
    """Заголовок с любыми символами должен давать честный отказ.

    hmac.compare_digest на строке с не-ASCII бросает TypeError — запрос
    заканчивался 500-й, то есть подделанный заголовок ронял эндпоинт вместо
    того, чтобы быть отвергнутым.
    """
    assert tokens_match(generate_csrf_token(), header) is False


def test_cookie_is_readable_by_javascript() -> None:
    """httponly=False обязателен: фронтенд читает куку, чтобы продублировать
    значение в заголовок. Секрета в токене нет."""
    response = Response()
    token = set_csrf_cookie(response)

    header = response.headers["set-cookie"]
    assert f"{CSRF_COOKIE_NAME}={token}" in header
    assert "httponly" not in header.lower()
    assert "path=/" in header.lower()


def test_set_csrf_cookie_accepts_explicit_token() -> None:
    response = Response()
    assert set_csrf_cookie(response, "fixed-value") == "fixed-value"
    assert "fixed-value" in response.headers["set-cookie"]


def test_delete_clears_cookie() -> None:
    response = Response()
    delete_csrf_cookie(response)
    header = response.headers["set-cookie"]
    assert CSRF_COOKIE_NAME in header
    assert "Max-Age=0" in header or "max-age=0" in header


def test_header_name_is_custom() -> None:
    """Заголовок должен быть нестандартным: простые заголовки браузер разрешает
    слать кросс-доменно без preflight, а X-CSRF-Token — нет."""
    assert CSRF_HEADER_NAME.lower().startswith("x-")
