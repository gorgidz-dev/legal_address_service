"""Справочник характеристик помещения продублирован на фронте — сверяем.

Копий три: app/enums.py (источник), frontend/src/types.ts (union-тип) и карта
подписей frontend/src/amenities.ts. Внутри фронта пропуск ловит компилятор —
карта объявлена как Record<AddressAmenity, AmenityMeta>. Расхождение между
Python и TypeScript не видит ни pytest, ни tsc: новая характеристика на
бэкенде доедет до карточки без подписи и иконки и просто не покажется.

Здесь же проверяем валидатор: он единственное, что стоит между чужим PATCH и
колонкой без ограничений (ARRAY(Text) примет любую строку).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.enums import ADDRESS_AMENITY_VALUES, AddressAmenity
from app.routers.owner_dashboard import AddressAmenitiesUpdate

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _typescript_union_values(source: str, type_name: str) -> set[str]:
    match = re.search(rf"export type {type_name} =(.+?);", source, re.DOTALL)
    assert match, f"union-тип {type_name} не найден"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _amenity_map_keys(source: str) -> set[str]:
    match = re.search(
        r"export const AMENITIES: Record<AddressAmenity, AmenityMeta> = \{(.+?)\n\};",
        source,
        re.DOTALL,
    )
    assert match, "карта AMENITIES не найдена"
    return set(re.findall(r"^\s{2}(\w+):", match.group(1), re.MULTILINE))


def _amenity_order_values(source: str) -> list[str]:
    match = re.search(
        r"export const AMENITY_ORDER: AddressAmenity\[\] = \[(.+?)\];",
        source,
        re.DOTALL,
    )
    assert match, "список AMENITY_ORDER не найден"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_frontend_union_matches_backend_enum() -> None:
    values = _typescript_union_values(
        (FRONTEND / "types.ts").read_text(encoding="utf-8"), "AddressAmenity"
    )
    assert values == {a.value for a in AddressAmenity}


def test_amenity_map_covers_every_backend_value() -> None:
    source = (FRONTEND / "amenities.ts").read_text(encoding="utf-8")
    assert _amenity_map_keys(source) == {a.value for a in AddressAmenity}


def test_amenity_order_lists_every_value_once() -> None:
    order = _amenity_order_values((FRONTEND / "amenities.ts").read_text(encoding="utf-8"))
    assert sorted(order) == sorted(a.value for a in AddressAmenity)
    assert len(order) == len(set(order)), "в AMENITY_ORDER есть повторы"


def test_validator_accepts_known_values_and_keeps_order() -> None:
    payload = AddressAmenitiesUpdate(amenities=["parking", "metro"])
    assert payload.amenities == ["parking", "metro"]


def test_validator_drops_duplicates_keeping_first() -> None:
    payload = AddressAmenitiesUpdate(amenities=["metro", "parking", "metro"])
    assert payload.amenities == ["metro", "parking"]


def test_validator_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError) as exc:
        AddressAmenitiesUpdate(amenities=["metro", "swimming_pool"])
    assert "swimming_pool" in str(exc.value)


def test_empty_list_is_valid() -> None:
    assert AddressAmenitiesUpdate().amenities == []
    assert AddressAmenitiesUpdate(amenities=[]).amenities == []


def test_enum_values_tuple_matches_enum() -> None:
    assert ADDRESS_AMENITY_VALUES == tuple(a.value for a in AddressAmenity)
