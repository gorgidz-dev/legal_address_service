"""Защита от CSRF по схеме double-submit cookie.

Зачем это нужно, если куки уже SameSite=lax. SameSite закрывает классический
сценарий (форма на чужом сайте отправляет POST с вашими куками), но остаётся
хвост, который на него не опирается:

- старые браузеры без поддержки SameSite отправляют куки как раньше;
- кука выставлена на домен `.uradres.net`, то есть её видит любой поддомен;
  скомпрометированный или чужой поддомен снимает защиту SameSite целиком —
  запрос с него для браузера «свой»;
- `lax` не действует на запросы, инициированные с того же сайта, — а значит
  на XSS-подобные сценарии внутри домена.

Схема: сервер кладёт случайный токен в НЕ-httponly куку, фронтенд читает её и
дублирует значение в заголовке `X-CSRF-Token`. Чужой сайт куку прочитать не
может (правило одного источника), поэтому подделать заголовок не в состоянии.

Проверка касается только запросов, авторизованных КУКОЙ. Клиенты с
`Authorization: Bearer` не подвержены CSRF: браузер такой заголовок сам не
подставляет, поэтому мобильное API проверку не проходит и не должно.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Response

from app.config import settings

CSRF_COOKIE_NAME = "uradres_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

#: Методы, которые не меняют состояние и потому не требуют токена.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

_TOKEN_BYTES = 32


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def set_csrf_cookie(response: Response, token: str | None = None) -> str:
    """Кладёт токен в куку и возвращает его.

    httponly=False намеренно: значение обязан прочитать JavaScript, чтобы
    продублировать его в заголовке. Секрета в токене нет — он бесполезен без
    сессионной куки, которая остаётся httponly.
    """
    value = token or generate_csrf_token()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        value,
        max_age=settings.web_session_ttl_hours * 3600,
        path="/",
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        domain=settings.session_cookie_domain,
    )
    return value


def delete_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        domain=settings.session_cookie_domain,
    )


def tokens_match(cookie_value: str | None, header_value: str | None) -> bool:
    """Сравнение в постоянном времени; пустые значения не совпадают никогда.

    Сравниваем байты, а не строки: `compare_digest` на строке с не-ASCII
    символами бросает TypeError, и заголовок вида `X-CSRF-Token: подделка`
    ронял бы запрос в 500 вместо честного отказа.
    """
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(
        cookie_value.encode("utf-8", "surrogatepass"),
        header_value.encode("utf-8", "surrogatepass"),
    )


def csrf_check_required(*, method: str, authenticated_by_cookie: bool) -> bool:
    if method.upper() in SAFE_METHODS:
        return False
    return authenticated_by_cookie
