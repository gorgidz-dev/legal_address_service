"""Витринный набор не должен ломать существующие эндпоинты."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.provider import ProviderRead
from scripts import seed_demo_providers as seeder


def _read_payload(**overrides):
    base = {
        "id": "0e2a3d4c-1111-2222-3333-444455556666",
        "code": "DEMO-001",
        "full_name": "Общество с ограниченной ответственностью «Астра Групп»",
        "short_name": "Астра Групп",
        "is_active": True,
        "created_at": "2026-07-26T00:00:00Z",
        "updated_at": "2026-07-26T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_provider_without_registry_numbers_serialises() -> None:
    """Демо-собственник без ИНН/ОГРН обязан проходить схему чтения.

    Регрессия: первая версия сидера подставляла выдуманные номера, схема
    проверяла их контрольные суммы, и GET /providers падал в 500 — админский
    раздел «Собственники» не открывался вовсе.
    """
    provider = ProviderRead.model_validate(_read_payload(inn=None, ogrn=None, kpp=None))
    assert provider.inn is None
    assert provider.ogrn is None


def test_invented_numbers_would_have_failed_validation() -> None:
    """Фиксируем причину: у выдуманного ИНН не сходится контрольная сумма."""
    with pytest.raises(ValidationError):
        ProviderRead.model_validate(_read_payload(inn="7700000001"))


def test_seed_data_declares_no_registry_numbers() -> None:
    """Страховка от возврата выдуманных реквизитов в сидер."""
    source = (seeder.__file__ or "")
    assert source
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "inn=None" in text
    assert "ogrn=None" in text


def test_listings_and_photos_are_consistent() -> None:
    """Каждой карточке — свой адрес и своё название компании."""
    assert len(seeder.LISTINGS) == 25
    addresses = {f"{city} {street}" for city, street, *_ in seeder.LISTINGS}
    assert len(addresses) == len(seeder.LISTINGS), "адреса не должны повторяться"
    assert len(seeder.COMPANY_NAMES) >= len(seeder.LISTINGS)
    # Все города должны иметь координаты, иначе карточка не попадёт на карту.
    for city, *_ in seeder.LISTINGS:
        assert city in seeder.CITY_COORDS
