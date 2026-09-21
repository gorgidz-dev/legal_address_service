"""Клиент интернет-эквайринга Т-Банка (API v2).

Разбор документации, ссылки на первоисточники и грабли — docs/tbank-acquiring.md.
Здесь только транспорт и подпись; что делать с заказом по статусу банка,
решает app/services/tbank_payments.py.

Подпись (Token) одинакова для наших запросов и для уведомлений банка:
корневые скалярные поля без самого Token (вложенные объекты и массивы —
Receipt, DATA, Data, Shops — не участвуют) + пара Password → сортировка по
ключу → склейка значений без разделителей → SHA-256 от UTF-8 → hex.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional

import certifi
import httpx

from app.config import settings
from app.services.dadata import CircuitBreaker  # тот же предохранитель, что у CDEK

log = logging.getLogger(__name__)

# API Т-Банка подписан сертификатом НУЦ Минцифры (Russian Trusted Sub CA) —
# в certifi его нет, и без этого файла httpx падает на «self-signed certificate
# in certificate chain». Проверено 21.09.2026 и с Windows, и из контейнера прода.
_RUSSIAN_TRUSTED_CA = Path(__file__).resolve().parent.parent / "certs" / "russian_trusted_ca.pem"


@lru_cache(maxsize=1)
def tbank_ssl_context() -> ssl.SSLContext:
    """certifi + НУЦ Минцифры. Именно объединение: только российский бандл
    лишил бы доверия к публичным УЦ, если банк вернётся на них. Проверка TLS
    не отключается — документация прямо запрещает это в production."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=str(_RUSSIAN_TRUSTED_CA))
    return context


# RedirectDueDate банк ждёт в виде YYYY-MM-DDTHH24:MI:SS+GMT, пример в документации
# с +03:00 — отдаём московское время, так же читается и в ЛК.
_MSK = timezone(timedelta(hours=3))


class TBankNotConfigured(RuntimeError):
    """TBANK_TERMINAL_KEY / TBANK_PASSWORD не заданы — интеграция выключена."""


class TBankError(RuntimeError):
    """Сеть, HTTP 5xx, невалидный ответ или бизнес-ошибка (Success=false)."""

    def __init__(self, message: str, *, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code

    @property
    def is_business_refusal(self) -> bool:
        """Банк явно отказал (Success=false с кодом). Сеть, таймаут и системный
        сбой 9999 — не отказ: исход операции неизвестен."""
        return self.error_code is not None and self.error_code != "9999"


# ============================================================
# Подпись
# ============================================================


def _token_value(value: Any) -> str:
    # Банк склеивает JSON-значения как есть: true → "true". Питоновский
    # str(True) дал бы "True" — и подпись каждого уведомления не сошлась бы.
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def make_token(params: Mapping[str, Any], password: str) -> str:
    """Token для запроса к API или для проверки уведомления.

    Набор полей берётся из того, что реально пришло или уходит, а не из
    фиксированного списка: у СБП нет CardId/ExpDate, при рекуррентах есть
    RebillId — захардкоженный список сломал бы подпись на первом новом поле.
    """
    pairs = {
        key: value
        for key, value in params.items()
        if key != "Token" and value is not None and not isinstance(value, (dict, list))
    }
    pairs["Password"] = password
    joined = "".join(_token_value(pairs[key]) for key in sorted(pairs))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def verify_notification_token(body: Mapping[str, Any], password: str) -> bool:
    received = body.get("Token")
    if not isinstance(received, str) or not received:
        return False
    # Любой мусор (не-ASCII, одинокие суррогаты из JSON-эскейпов) — это «подпись
    # не совпала», а не 500: compare_digest на str с не-ASCII бросает TypeError,
    # а encode суррогата — UnicodeEncodeError.
    try:
        expected = make_token(body, password).encode("ascii")
        return hmac.compare_digest(expected, received.lower().encode("utf-8"))
    except (UnicodeError, TypeError):
        return False


# ============================================================
# Ответы
# ============================================================


@dataclass(frozen=True)
class TBankInitResult:
    payment_id: str  # PaymentId — строкой: число не влезает в JS без потери точности
    payment_url: str
    status: str


@dataclass(frozen=True)
class TBankState:
    payment_id: str
    status: str
    amount_kopeks: Optional[int]
    order_id: Optional[str] = None  # наш Payment.id, переданный в Init


@dataclass(frozen=True)
class TBankCancelResult:
    status: str
    original_amount_kopeks: Optional[int]
    new_amount_kopeks: Optional[int]  # остаток после операции


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ============================================================
# HTTP-клиент
# ============================================================


class TBankClient:
    def __init__(self, *, terminal_key: str, password: str, base_url: str, timeout: float):
        if not terminal_key or not password:
            raise TBankNotConfigured("TBANK_TERMINAL_KEY / TBANK_PASSWORD не заданы")
        self.terminal_key = terminal_key
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def is_demo(self) -> bool:
        return self.terminal_key.upper().endswith("DEMO")

    def verify_notification(self, body: Mapping[str, Any]) -> bool:
        return verify_notification_token(body, self._password)

    async def init(
        self,
        *,
        amount_kopeks: int,
        order_id: str,
        description: str,
        notification_url: str,
        success_url: str,
        fail_url: str,
        redirect_due: datetime,
        receipt: Optional[dict[str, Any]] = None,
    ) -> TBankInitResult:
        params: dict[str, Any] = {
            "Amount": int(amount_kopeks),
            "OrderId": order_id,
            # В спецификации maxLength 140; при СБП текст виден в мобильном банке.
            "Description": description[:140],
            "PayType": "O",  # одностадийная: СБП двухстадийной не бывает
            "NotificationURL": notification_url,
            "SuccessURL": success_url,
            "FailURL": fail_url,
            "RedirectDueDate": redirect_due.astimezone(_MSK).strftime("%Y-%m-%dT%H:%M:%S+03:00"),
        }
        if receipt is not None:
            params["Receipt"] = receipt  # в подпись не входит — make_token пропускает объекты
        data = await self._call("Init", params)
        payment_id, payment_url = data.get("PaymentId"), data.get("PaymentURL")
        if payment_id is None or not payment_url:
            raise TBankError(f"Init: нет PaymentId/PaymentURL в ответе: {data}")
        return TBankInitResult(
            payment_id=str(payment_id),
            payment_url=str(payment_url),
            status=str(data.get("Status") or ""),
        )

    async def get_state(self, *, payment_id: str) -> TBankState:
        data = await self._call("GetState", {"PaymentId": payment_id})
        status = data.get("Status")
        if not status:
            raise TBankError(f"GetState: нет Status в ответе: {data}")
        return TBankState(
            payment_id=str(data.get("PaymentId") or payment_id),
            status=str(status),
            amount_kopeks=_as_int(data.get("Amount")),
            order_id=None if data.get("OrderId") is None else str(data.get("OrderId")),
        )

    async def cancel(
        self,
        *,
        payment_id: str,
        amount_kopeks: Optional[int] = None,
        external_request_id: Optional[str] = None,
        receipt: Optional[dict[str, Any]] = None,
    ) -> TBankCancelResult:
        """Отмена (до оплаты) или возврат (после). Без Amount — на всю сумму Init."""
        params: dict[str, Any] = {"PaymentId": payment_id}
        if amount_kopeks is not None:
            params["Amount"] = int(amount_kopeks)
        if external_request_id:
            # Ключ идемпотентности возврата: повтор не создаст второй возврат.
            params["ExternalRequestId"] = external_request_id
        if receipt is not None:
            params["Receipt"] = receipt
        data = await self._call("Cancel", params)
        return TBankCancelResult(
            status=str(data.get("Status") or ""),
            original_amount_kopeks=_as_int(data.get("OriginalAmount")),
            new_amount_kopeks=_as_int(data.get("NewAmount")),
        )

    async def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        body = {"TerminalKey": self.terminal_key, **params}
        body["Token"] = make_token(body, self._password)
        url = f"{self._base_url}/{method}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=tbank_ssl_context()) as client:
                resp = await client.post(url, json=body)
        except httpx.HTTPError as e:
            raise TBankError(f"Т-Банк недоступен ({method}): {e}") from e

        try:
            data = resp.json()
        except ValueError as e:
            raise TBankError(f"Т-Банк {method}: HTTP {resp.status_code}, ответ не JSON") from e
        if not isinstance(data, dict):
            raise TBankError(f"Т-Банк {method}: ответ не объект")

        # Бизнес-ошибки приходят с HTTP 200 и Success=false; системные — HTTP 500.
        if resp.status_code >= 400 or data.get("Success") is not True:
            code = data.get("ErrorCode")
            message = data.get("Message") or data.get("Details") or f"HTTP {resp.status_code}"
            details = data.get("Details")
            if details and details != message:
                message = f"{message} ({details})"
            raise TBankError(
                f"Т-Банк {method}: {message} [код {code}]",
                error_code=None if code is None else str(code),
            )
        return data


# ============================================================
# Сервис: клиент + предохранитель
# ============================================================


class TBankService:
    def __init__(self, client: TBankClient, breaker: CircuitBreaker):
        self._client = client
        self._breaker = breaker

    @property
    def terminal_key(self) -> str:
        return self._client.terminal_key

    @property
    def is_demo(self) -> bool:
        return self._client.is_demo

    def verify_notification(self, body: Mapping[str, Any]) -> bool:
        return self._client.verify_notification(body)

    async def init(self, **kwargs) -> TBankInitResult:
        return await self._wrap(lambda: self._client.init(**kwargs))

    async def get_state(self, *, payment_id: str) -> TBankState:
        return await self._wrap(lambda: self._client.get_state(payment_id=payment_id))

    async def cancel(self, **kwargs) -> TBankCancelResult:
        return await self._wrap(lambda: self._client.cancel(**kwargs))

    async def _wrap(self, op):
        if not self._breaker.allow_request():
            raise TBankError("Т-Банк временно недоступен (предохранитель открыт).")
        try:
            result = await op()
        except TBankError as e:
            # Бизнес-отказ (Success=false с кодом) — не признак недоступности
            # банка: не копим его в предохранитель, иначе три отказа по чужим
            # заказам закрыли бы оплату всем.
            if not e.is_business_refusal:
                self._breaker.record_failure()
            raise
        self._breaker.record_success()
        return result


_service: Optional[TBankService] = None


def get_tbank_service() -> TBankService:
    global _service
    if _service is None:
        if not settings.tbank_terminal_key or not settings.tbank_password:
            raise TBankNotConfigured(
                "Оплата картой и по СБП не подключена: TBANK_TERMINAL_KEY / "
                "TBANK_PASSWORD не заданы."
            )
        _service = TBankService(
            TBankClient(
                terminal_key=settings.tbank_terminal_key,
                password=settings.tbank_password,
                base_url=settings.tbank_base_url,
                timeout=settings.tbank_request_timeout_seconds,
            ),
            CircuitBreaker(
                failure_threshold=settings.tbank_circuit_failure_threshold,
                recovery_seconds=settings.tbank_circuit_recovery_seconds,
            ),
        )
    return _service


def reset_tbank_service() -> None:
    """Для тестов."""
    global _service
    _service = None
