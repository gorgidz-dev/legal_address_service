"""DaData address-suggest — структурный разбор адреса: регион, город, ИФНС.

Отдельно от dadata.py (там party API по ИНН). Здесь — suggest по тексту адреса:
DaData возвращает region / city / tax_office (код ИФНС). Используется при
создании адреса, чтобы заполнить справочник fns_offices и addresses.fns_office_id.

Адреса заводятся редко (staff), поэтому без circuit-breaker и кэша — простой
прямой вызов. Если DaData не настроена/недоступна — возвращаем None, создание
адреса не блокируется (гео-привязку можно проставить позже).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

DADATA_ADDRESS_URL = (
    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
)
_TIMEOUT_SECONDS = 8.0


@dataclass
class DaDataAddressResult:
    """Структурный результат разбора адреса."""

    region: str
    city: str
    fns_code: Optional[str]          # федеральный код ИФНС, напр. "7746"
    fns_short_number: Optional[int]  # локальный номер, напр. 46
    fns_name: Optional[str]          # сконструированное имя инспекции
    geo_lat: Optional[float]         # широта (geo_lat DaData), для карты
    geo_lon: Optional[float]         # долгота (geo_lon DaData), для карты


def _parse_suggestion(data: dict) -> Optional[DaDataAddressResult]:
    """Извлекает регион/город/ИФНС из data одного suggestion'а DaData."""
    region = (data.get("region") or "").strip()
    if not region:
        return None
    # У городов федерального значения (Москва/СПб) city пустой — это и регион,
    # и город одновременно. Иначе берём город или нас. пункт.
    city = (
        data.get("city")
        or data.get("settlement")
        or region
    ).strip()

    fns_code = (data.get("tax_office") or data.get("tax_office_legal") or "").strip()
    fns_short: Optional[int] = None
    fns_name: Optional[str] = None
    if fns_code:
        # Локальный номер — последние 2 цифры 4-значного кода (7746 → 46).
        tail = fns_code[-2:]
        if tail.isdigit():
            fns_short = int(tail)
        label_num = fns_short if fns_short is not None else fns_code
        fns_name = f"ИФНС России № {label_num} по {city}"

    def _to_float(value: object) -> Optional[float]:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return DaDataAddressResult(
        region=region,
        city=city,
        fns_code=fns_code or None,
        fns_short_number=fns_short,
        fns_name=fns_name,
        geo_lat=_to_float(data.get("geo_lat")),
        geo_lon=_to_float(data.get("geo_lon")),
    )


async def suggest_address(query: str) -> Optional[DaDataAddressResult]:
    """Разбирает адрес через DaData. None — если не настроено / не найдено / ошибка."""
    token = settings.dadata_token
    if not token or not query.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                DADATA_ADDRESS_URL,
                json={"query": query, "count": 1},
                headers={
                    "Authorization": f"Token {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("DaData address-suggest failed for %r: %s", query[:60], e)
        return None

    suggestions = payload.get("suggestions") or []
    if not suggestions:
        return None
    return _parse_suggestion(suggestions[0].get("data") or {})


async def geocode(query: str) -> Optional[tuple[float, float]]:
    """Координаты (latitude, longitude) адреса через DaData. None — нет точки.

    Использует тот же address-suggest, что и разбор региона/ИФНС, — отдельный
    геокодер не нужен. DaData отдаёт geo_lat/geo_lon в data.
    """
    result = await suggest_address(query)
    if result is None or result.geo_lat is None or result.geo_lon is None:
        return None
    return (result.geo_lat, result.geo_lon)
