"""Геокодер Яндекса — превращает текстовый адрес в координаты (lat, lon).

HTTP Geocoder API: https://geocode-maps.yandex.ru/1.x/. Серверный ключ берётся
из settings.yandex_geocoder_key (env YANDEX_GEOCODER_KEY).

Адреса заводятся редко (staff/сидер), поэтому без circuit-breaker и кэша —
простой прямой вызов. Ключ пустой или точка не найдена → возвращаем None,
создание адреса не блокируется (координаты можно проставить позже бэкфиллом).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"
_TIMEOUT_SECONDS = 8.0


async def geocode(address: str) -> Optional[tuple[float, float]]:
    """Возвращает (latitude, longitude) для адреса или None.

    None — если ключ не задан, сеть недоступна или адрес не распознан.
    """
    query = (address or "").strip()
    if not query or not settings.yandex_geocoder_key:
        return None

    params = {
        "apikey": settings.yandex_geocoder_key,
        "geocode": query,
        "format": "json",
        "results": 1,
        "lang": "ru_RU",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(GEOCODER_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Yandex geocoder failed for %r: %s", query, exc)
        return None

    try:
        members = (
            data["response"]["GeoObjectCollection"]["featureMember"]
        )
        if not members:
            return None
        # Point.pos — строка "долгота широта" (порядок: lon lat).
        pos: str = members[0]["GeoObject"]["Point"]["pos"]
        lon_str, lat_str = pos.split()
        return (float(lat_str), float(lon_str))
    except (KeyError, IndexError, ValueError) as exc:
        log.warning("Yandex geocoder unexpected response for %r: %s", query, exc)
        return None
