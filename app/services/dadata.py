"""
DaData party API — клиент + сервис с in-memory TTL-кэшем.

Использование:
    service = get_dadata_service()
    result = await service.lookup("7707083893")  # → DaDataLookupResponse | None

Эндпоинт `/clients/lookup-by-inn` использует именно этот сервис через
get_dadata_service(); кэш живёт 24 часа на ИНН (DaData стоит денег за вызов).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from app.config import settings
from app.enums import EgrulStatus
from app.schemas.client import DaDataLookupResponse

log = logging.getLogger(__name__)

DADATA_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_CACHE_TTL_SECONDS = 24 * 3600


class DaDataNotConfigured(RuntimeError):
    """Токен DaData не задан в настройках — сервис не может работать."""


class DaDataError(RuntimeError):
    """Ошибка обращения к DaData (сеть, 5xx, невалидный JSON)."""


# ============================================================
# Маппинг ответа DaData → наша схема
# ============================================================

def map_party_to_lookup(party: dict[str, Any]) -> DaDataLookupResponse:
    """
    Превращает DaData party suggestion в DaDataLookupResponse.

    Чистая функция, удобно тестировать с фикстурой без HTTP-запроса.
    """
    data = party.get("data") or {}
    name = data.get("name") or {}
    state = data.get("state") or {}
    management = data.get("management") or {}
    address = data.get("address") or {}
    address_data = address.get("data") or {}
    # Основной ОКВЭД: сначала ищем элемент с main=True, иначе берём первый из списка.
    # Если списка нет — пробуем плоское поле data.okved (там только код).
    okveds = data.get("okveds") or []
    main_okved = next((o for o in okveds if o.get("main")), None) or (okveds[0] if okveds else None)
    if main_okved is None and data.get("okved"):
        main_okved = {"code": data["okved"], "name": None}

    status_raw = state.get("status") or "ACTIVE"
    try:
        egrul_status = EgrulStatus(status_raw)
    except ValueError:
        log.warning("Неизвестный статус ЕГРЮЛ от DaData: %r — fallback на ACTIVE", status_raw)
        egrul_status = EgrulStatus.ACTIVE

    blockers = DaDataLookupResponse.Blockers(
        liquidating_or_liquidated=egrul_status in (EgrulStatus.LIQUIDATING, EgrulStatus.LIQUIDATED),
        bankrupt=egrul_status == EgrulStatus.BANKRUPT,
        signatory_disqualified=bool(management.get("disqualified")),
        is_branch=(data.get("branch_type") or "MAIN") != "MAIN",
    )

    return DaDataLookupResponse(
        inn=data["inn"],
        kpp=data.get("kpp"),
        ogrn=data.get("ogrn"),
        full_name=name.get("full_with_opf") or name.get("full") or "",
        short_name=name.get("short_with_opf") or name.get("short") or "",
        legal_address=address.get("unrestricted_value") or address.get("value"),
        kladr_id=address_data.get("kladr_id"),
        signatory_name=management.get("name"),
        signatory_position=management.get("post"),
        okved_main_code=main_okved.get("code") if main_okved else None,
        okved_main_name=main_okved.get("name") if main_okved else None,
        egrul_status=egrul_status,
        blockers=blockers,
    )


# ============================================================
# HTTP-клиент DaData
# ============================================================

class DaDataClient:
    """Тонкая обёртка над party API. Поднимает DaDataError на любой проблеме сети/5xx."""

    def __init__(self, token: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        if not token:
            raise DaDataNotConfigured("DADATA_TOKEN не задан")
        self._token = token
        self._timeout = timeout

    async def find_by_inn(self, inn: str) -> Optional[dict[str, Any]]:
        """Вернёт первое попадание из suggestions или None, если ЮЛ не найдено."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    DADATA_PARTY_URL,
                    json={"query": inn, "branch_type": "MAIN"},
                    headers={
                        "Authorization": f"Token {self._token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise DaDataError(f"DaData недоступна: {e}") from e

        try:
            payload = resp.json()
        except ValueError as e:
            raise DaDataError(f"Невалидный JSON от DaData: {e}") from e

        suggestions = payload.get("suggestions") or []
        return suggestions[0] if suggestions else None


# ============================================================
# Кэш + сервис
# ============================================================

class _TTLCache:
    """Простой in-memory кэш с TTL. На случай гонок — лишняя запись безопасна."""

    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, ts = entry
        if time.time() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.time())

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)


class CircuitBreaker:
    """Three-state breaker: closed (normal) → open (skip calls) → half_open (one trial).

    After `failure_threshold` consecutive failures the breaker opens for
    `recovery_seconds`. While open, callers see DaDataError immediately —
    no HTTP request goes out. After the recovery window a single trial is
    allowed (half_open); success closes, failure re-opens.

    Protects against cascading slowness when DaData is down: rather than
    every request hanging for 10s, they fast-fail.
    """

    def __init__(self, *, failure_threshold: int, recovery_seconds: float):
        self._threshold = max(1, failure_threshold)
        self._recovery = recovery_seconds
        self._consecutive_failures = 0
        self._opened_at: Optional[float] = None

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self._recovery:
            return "half_open"
        return "open"

    def allow_request(self) -> bool:
        return self.state in {"closed", "half_open"}

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._threshold:
            self._opened_at = time.monotonic()


class DaDataService:
    """Сервис: HTTP-клиент + кэш + circuit breaker + маппинг ответа в Pydantic-схему."""

    def __init__(
        self,
        token: str,
        *,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        breaker: Optional[CircuitBreaker] = None,
    ):
        self._client = DaDataClient(token)
        self._cache = _TTLCache(cache_ttl_seconds)
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=3, recovery_seconds=30.0
        )

    async def lookup(self, inn: str) -> Optional[DaDataLookupResponse]:
        """Найти ЮЛ по ИНН. Использует кэш + circuit breaker."""
        cached = self._cache.get(inn)
        if cached is not None:
            return cached

        if not self._breaker.allow_request():
            raise DaDataError(
                "DaData временно недоступна (circuit breaker открыт после серии ошибок). Повторите позже."
            )

        try:
            party = await self._client.find_by_inn(inn)
        except DaDataError:
            self._breaker.record_failure()
            raise

        self._breaker.record_success()

        if party is None:
            return None

        result = map_party_to_lookup(party)
        self._cache.set(inn, result)
        return result

    def invalidate(self, inn: str) -> None:
        self._cache.invalidate(inn)


# ============================================================
# Singleton-доступ к сервису (используется в FastAPI Depends)
# ============================================================

_service: Optional[DaDataService] = None


def get_dadata_service() -> DaDataService:
    """Lazy-singleton. Бросает DaDataNotConfigured, если токен не задан."""
    global _service
    if _service is None:
        if not settings.dadata_token:
            raise DaDataNotConfigured(
                "DADATA_TOKEN не задан. Получить ключ можно на dadata.ru (бесплатный тариф — "
                "10 000 запросов/день), затем положить в .env: DADATA_TOKEN=..."
            )
        _service = DaDataService(
            settings.dadata_token,
            breaker=CircuitBreaker(
                failure_threshold=settings.dadata_circuit_failure_threshold,
                recovery_seconds=settings.dadata_circuit_recovery_seconds,
            ),
        )
    return _service


def reset_dadata_service() -> None:
    """Для тестов и горячей перезагрузки настроек."""
    global _service
    _service = None
