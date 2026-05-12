"""CDEK Pay client (SBP for individuals first).

Подпись:
    flatten(payment_order) → sort keys ABC → join values "|" → append secret_key
    → SHA256 hex → UPPERCASE.

Callback подпись считается по тому же алгоритму над содержимым `payment`.

Окружение задаёт боевую/тестовую среду через `cdek_currency` (RUR | TST).
Если `cdek_login` или `cdek_secret_key` пустые — сервис считается выключённым,
и вызывающий код должен поднимать 503.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.dadata import CircuitBreaker  # reuse the breaker implementation

log = logging.getLogger(__name__)


class CdekPayNotConfigured(RuntimeError):
    """CDEK_LOGIN / CDEK_SECRET_KEY не заданы — интеграция выключена."""


class CdekPayError(RuntimeError):
    """Сеть, 5xx, невалидный JSON, или 4xx с message."""


# ============================================================
# Signature
# ============================================================


def _flatten(prefix: str, value: Any, out: list[tuple[str, Any]]) -> None:
    """Recursively flatten nested dicts/lists into [(dotted_key, leaf_value), ...]."""
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else k
            _flatten(child, v, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            child = f"{prefix}.{i}" if prefix else str(i)
            _flatten(child, v, out)
    else:
        out.append((prefix, value))


def sign_payment_order(payment_order: dict[str, Any], secret_key: str) -> str:
    """Compute the CDEK Pay signature for a `payment_order` (or `payment` callback) dict.

    Steps as documented:
        1. Flatten nested objects to dotted keys (receipt_details.0.id etc.).
        2. Sort keys alphabetically.
        3. Join values with `|`, then append `|secret_key`.
        4. SHA256 hex, upper-cased.
    """
    pairs: list[tuple[str, Any]] = []
    _flatten("", payment_order, pairs)
    pairs.sort(key=lambda kv: kv[0])
    parts = [_stringify(v) for _, v in pairs]
    parts.append(secret_key)
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest().upper()


def _stringify(value: Any) -> str:
    """Match the docs' canonical rendering: ints/floats without `.0`, bools as 'true'/'false'."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def verify_callback_signature(
    payment_payload: dict[str, Any],
    signature: str,
    secret_key: str,
) -> bool:
    """Constant-time-ish compare between the supplied signature and our recomputation.

    The docs use upper-case hex; we compare case-insensitively to be safe.
    """
    expected = sign_payment_order(payment_payload, secret_key)
    return _consteq(expected.upper(), (signature or "").upper())


def _consteq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ============================================================
# Responses
# ============================================================


@dataclass(frozen=True)
class CdekQrResponse:
    qr_link: str
    qr_image_base64: str
    order_id: int
    access_key: str


# ============================================================
# HTTP client
# ============================================================


class CdekPayClient:
    def __init__(
        self,
        *,
        login: str,
        secret_key: str,
        base_url: str,
        currency: str,
        timeout: float,
    ):
        if not login or not secret_key:
            raise CdekPayNotConfigured("CDEK_LOGIN / CDEK_SECRET_KEY не заданы")
        self._login = login
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._currency = currency
        self._timeout = timeout

    async def generate_sbp_qr(
        self,
        *,
        amount_kopeks: int,
        pay_for: str,
        qr_life_time_minutes: int,
        user_phone: Optional[str] = None,
        user_email: Optional[str] = None,
        return_url_success: Optional[str] = None,
        return_url_fail: Optional[str] = None,
        pay_for_details: Optional[dict[str, Any]] = None,
    ) -> CdekQrResponse:
        payment_order: dict[str, Any] = {
            "qr_life_time": int(qr_life_time_minutes),
            "pay_for": pay_for,
            "pay_amount": int(amount_kopeks),
            "currency": self._currency,
        }
        if user_phone:
            payment_order["user_phone"] = user_phone
        if user_email:
            payment_order["user_email"] = user_email
        if return_url_success:
            payment_order["return_url_success"] = return_url_success
        if return_url_fail:
            payment_order["return_url_fail"] = return_url_fail
        if pay_for_details:
            payment_order["pay_for_details"] = pay_for_details

        body = {
            "login": self._login,
            "signature": sign_payment_order(payment_order, self._secret_key),
            "payment_order": payment_order,
        }
        data = await self._post("/merchant_api/sbp_qrs", body)
        try:
            return CdekQrResponse(
                qr_link=data["qr_link"],
                qr_image_base64=data["qr_image"],
                order_id=int(data["order_id"]),
                access_key=str(data["access_key"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise CdekPayError(f"Неожиданный формат ответа sbp_qrs: {data}") from e

    async def block_payment_link(self, *, access_key: str) -> None:
        # access_key + secret_key, joined by "|"
        sig_raw = f"{access_key}|{self._secret_key}"
        signature = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest().upper()
        url = f"/merchant_api/payment_orders/{access_key}/block"
        params = {"login": self._login, "signature": signature}
        await self._post(url, body=None, params=params)

    async def request_refund(
        self,
        *,
        payment_id: int,
        value_refund_kopeks: int,
        reason: str,
    ) -> dict[str, Any]:
        data = {
            "payment_id": int(payment_id),
            "value_refund": int(value_refund_kopeks),
            "reason": reason,
        }
        body = {
            "login": self._login,
            "signature": sign_payment_order(data, self._secret_key),
            "data": data,
        }
        return await self._post("/merchant_api/cancellation_requests", body)

    async def _post(
        self,
        path: str,
        body: Optional[dict[str, Any]],
        *,
        params: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        url = self._base_url + path
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=body, params=params)
        except httpx.HTTPError as e:
            raise CdekPayError(f"CDEK Pay недоступен: {e}") from e

        if resp.status_code >= 400:
            try:
                err_payload = resp.json()
            except ValueError:
                err_payload = resp.text
            raise CdekPayError(f"CDEK Pay {resp.status_code}: {err_payload}")

        # Some endpoints (e.g. block) may return empty body
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as e:
            raise CdekPayError(f"Невалидный JSON от CDEK Pay: {e}") from e


# ============================================================
# Service (client + breaker)
# ============================================================


class CdekPayService:
    def __init__(self, client: CdekPayClient, breaker: CircuitBreaker):
        self._client = client
        self._breaker = breaker

    @property
    def currency(self) -> str:
        return self._client._currency

    @property
    def secret_key(self) -> str:
        # exposed for callback verification — the webhook handler needs it.
        return self._client._secret_key

    async def generate_sbp_qr(self, **kwargs) -> CdekQrResponse:
        return await self._wrap(lambda: self._client.generate_sbp_qr(**kwargs))

    async def block_payment_link(self, *, access_key: str) -> None:
        await self._wrap(lambda: self._client.block_payment_link(access_key=access_key))

    async def request_refund(self, **kwargs) -> dict[str, Any]:
        return await self._wrap(lambda: self._client.request_refund(**kwargs))

    async def _wrap(self, op):
        if not self._breaker.allow_request():
            raise CdekPayError("CDEK Pay временно недоступен (circuit breaker открыт).")
        try:
            result = await op()
        except CdekPayError:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return result


# ============================================================
# Singleton
# ============================================================

_service: Optional[CdekPayService] = None


def get_cdek_pay_service() -> CdekPayService:
    global _service
    if _service is None:
        if not settings.cdek_login or not settings.cdek_secret_key:
            raise CdekPayNotConfigured(
                "CDEK_LOGIN / CDEK_SECRET_KEY не заданы. Включить интеграцию: "
                "получить логин/ключ в личном кабинете https://secure.cdekfin.ru/stores и "
                "положить в .env."
            )
        client = CdekPayClient(
            login=settings.cdek_login,
            secret_key=settings.cdek_secret_key,
            base_url=settings.cdek_base_url,
            currency=settings.cdek_currency,
            timeout=settings.cdek_request_timeout_seconds,
        )
        _service = CdekPayService(
            client,
            CircuitBreaker(
                failure_threshold=settings.cdek_circuit_failure_threshold,
                recovery_seconds=settings.cdek_circuit_recovery_seconds,
            ),
        )
    return _service


def reset_cdek_pay_service() -> None:
    """Для тестов."""
    global _service
    _service = None
