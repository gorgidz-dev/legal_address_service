"""Разбор города и сборка кода инспекции в scripts/seed_fns_offices.

Скрипт бэкфиллит addresses.fns_office_id, от которого зависит весь каскад
«Регион → Город → ИФНС». Ошибка в разборе города тихо оставит адрес без
привязки, поэтому чистые функции проверяем без базы.
"""
from __future__ import annotations

import pytest

from scripts.seed_fns_offices import (
    CITIES,
    office_code,
    office_name,
    resolve_city,
)


@pytest.mark.parametrize(
    ("dative", "expected_city", "expected_region"),
    [
        ("Москве", "Москва", "Москва"),
        ("Екатеринбургу", "Екатеринбург", "Свердловская область"),
        ("Нижнему Новгороду", "Нижний Новгород", "Нижегородская область"),
        ("Ростову-на-Дону", "Ростов-на-Дону", "Ростовская область"),
        ("Санкт-Петербургу", "Санкт-Петербург", "Санкт-Петербург"),
    ],
)
def test_resolve_city_by_dative(dative, expected_city, expected_region):
    """Основной путь: город берётся из fns_city, как он лежит в базе."""
    ref = resolve_city("г. Что-угодно, ул. Какая-то, д. 1", dative)
    assert ref is not None
    assert ref.city == expected_city
    assert ref.region == expected_region


@pytest.mark.parametrize(
    ("full_address", "expected_city"),
    [
        ("г. Нижний Новгород, ул. Максима Горького, д. 117", "Нижний Новгород"),
        ("г. Ростов-на-Дону, ул. Красноармейская, д. 200", "Ростов-на-Дону"),
        ("Московская обл., г. Химки, Ленинградское ш., д. 16, оф. 33", "Химки"),
        ("г. Москва, ул. Профсоюзная, д. 84/32, корп. 1", "Москва"),
    ],
)
def test_resolve_city_by_address_when_no_dative(full_address, expected_city):
    """Запасной путь: у адреса не заполнен fns_city."""
    ref = resolve_city(full_address, None)
    assert ref is not None
    assert ref.city == expected_city


def test_resolve_city_unknown_returns_none():
    """Незнакомый город не подставляется наугад — адрес попадёт в отчёт."""
    assert resolve_city("г. Норильск, ул. Мира, д. 1", "Норильску") is None
    assert resolve_city(None, None) is None


def test_office_code_is_region_plus_padded_number():
    assert office_code("66", 39) == "6639"
    assert office_code("77", 3) == "7703"
    assert office_code("02", 40) == "0240"


def test_office_code_unique_across_regions_for_same_number():
    """Ровно то, что ломала прежняя версия: один номер в разных субъектах."""
    moscow = office_code("77", 46)
    spb = office_code("78", 46)
    assert moscow != spb


def test_office_name_prefers_stored_dative():
    ref = next(r for r in CITIES if r.city == "Нижний Новгород")
    assert office_name(52, ref, "Нижнему Новгороду") == (
        "ИФНС России № 52 по Нижнему Новгороду"
    )
    # fns_city пуст — падеж берём из справочника.
    assert office_name(52, ref, None) == "ИФНС России № 52 по Нижнему Новгороду"


def test_city_reference_is_consistent():
    """Дательные формы и названия уникальны, коды субъектов двузначные."""
    assert len({r.dative for r in CITIES}) == len(CITIES)
    assert len({r.city for r in CITIES}) == len(CITIES)
    for ref in CITIES:
        assert len(ref.region_code) == 2 and ref.region_code.isdigit()
