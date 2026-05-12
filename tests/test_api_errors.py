from __future__ import annotations

import json

import pytest
from fastapi import HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api_errors import (
    _http_exception_handler,
    _unhandled_handler,
    _validation_handler,
    code_for_status,
)
from app.main import app


def test_code_for_status_known_codes() -> None:
    assert code_for_status(401) == "unauthorized"
    assert code_for_status(403) == "forbidden"
    assert code_for_status(404) == "not_found"
    assert code_for_status(409) == "conflict"
    assert code_for_status(422) == "validation_error"
    assert code_for_status(429) == "rate_limited"
    assert code_for_status(500) == "internal_error"


def test_code_for_status_unknown_falls_back() -> None:
    assert code_for_status(418) == "http_418"


def test_middleware_unauthorized_uses_error_envelope() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    body = response.json()
    assert body == {"error": {"code": "unauthorized", "message": "Требуется вход"}}


def test_validation_error_envelope_carries_details() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) > 0


@pytest.mark.asyncio
async def test_http_exception_handler_404_shape() -> None:
    exc = StarletteHTTPException(status_code=404, detail="Ничего не найдено")
    response = await _http_exception_handler(None, exc)  # type: ignore[arg-type]
    assert response.status_code == 404
    payload = json.loads(response.body)
    assert payload == {"error": {"code": "not_found", "message": "Ничего не найдено"}}


@pytest.mark.asyncio
async def test_http_exception_handler_preserves_retry_after_header() -> None:
    exc = HTTPException(
        status_code=429,
        detail="Слишком часто",
        headers={"Retry-After": "60"},
    )
    response = await _http_exception_handler(None, exc)  # type: ignore[arg-type]
    assert response.status_code == 429
    assert response.headers.get("retry-after") == "60"
    payload = json.loads(response.body)
    assert payload["error"]["code"] == "rate_limited"
    assert payload["error"]["message"] == "Слишком часто"


@pytest.mark.asyncio
async def test_http_exception_handler_accepts_structured_detail() -> None:
    exc = HTTPException(
        status_code=409,
        detail={"code": "address_locked", "message": "Адрес занят", "details": {"holder": "u123"}},
    )
    response = await _http_exception_handler(None, exc)  # type: ignore[arg-type]
    assert response.status_code == 409
    payload = json.loads(response.body)
    assert payload == {
        "error": {
            "code": "address_locked",
            "message": "Адрес занят",
            "details": {"holder": "u123"},
        }
    }


@pytest.mark.asyncio
async def test_unhandled_exception_returns_500_envelope() -> None:
    class _FakeRequest:
        class _URL:
            path = "/x"

        method = "GET"
        url = _URL()

    response = await _unhandled_handler(_FakeRequest(), RuntimeError("boom"))  # type: ignore[arg-type]
    assert response.status_code == 500
    payload = json.loads(response.body)
    assert payload == {
        "error": {"code": "internal_error", "message": "Внутренняя ошибка сервиса"}
    }
