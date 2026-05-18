"""Гео-каскад: разбор адреса DaData + дерево Регион→Город→ИФНС."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.routers.marketplace import public_geo_tree
from app.services.dadata_address import _parse_suggestion


# ----------------------------- _parse_suggestion -----------------------------

def test_parse_suggestion_regular_city():
    data = {
        "region": "Московская",
        "city": "Химки",
        "tax_office": "5047",
    }
    r = _parse_suggestion(data)
    assert r is not None
    assert r.region == "Московская"
    assert r.city == "Химки"
    assert r.fns_code == "5047"
    assert r.fns_short_number == 47
    assert "47" in r.fns_name


def test_parse_suggestion_federal_city_moscow():
    """У Москвы city пустой — это и регион, и город."""
    data = {"region": "Москва", "city": None, "tax_office": "7746"}
    r = _parse_suggestion(data)
    assert r is not None
    assert r.region == "Москва"
    assert r.city == "Москва"
    assert r.fns_short_number == 46


def test_parse_suggestion_no_tax_office():
    data = {"region": "Москва", "city": None}
    r = _parse_suggestion(data)
    assert r is not None
    assert r.fns_code is None
    assert r.fns_short_number is None
    assert r.fns_name is None


def test_parse_suggestion_no_region_returns_none():
    assert _parse_suggestion({"city": "Где-то"}) is None


# ----------------------------- public_geo_tree -----------------------------

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Result(self._rows)


@pytest.mark.asyncio
async def test_geo_tree_nests_flat_rows():
    o1, o2, o3 = uuid4(), uuid4(), uuid4()
    # (region, city, office_id, short_number, name, count)
    rows = [
        ("Москва", "Москва", o1, 4, "ИФНС № 4", 2),
        ("Москва", "Москва", o2, 46, "ИФНС № 46", 3),
        ("Московская", "Химки", o3, 47, "ИФНС № 47", 1),
    ]
    tree = await public_geo_tree(db=_FakeSession(rows))

    assert len(tree) == 2
    moscow = next(r for r in tree if r["region"] == "Москва")
    assert moscow["count"] == 5  # 2 + 3
    assert len(moscow["cities"]) == 1
    assert moscow["cities"][0]["city"] == "Москва"
    assert moscow["cities"][0]["count"] == 5
    assert len(moscow["cities"][0]["offices"]) == 2

    mo = next(r for r in tree if r["region"] == "Московская")
    assert mo["count"] == 1
    assert mo["cities"][0]["city"] == "Химки"
    assert mo["cities"][0]["offices"][0]["short_number"] == 47


@pytest.mark.asyncio
async def test_geo_tree_empty():
    tree = await public_geo_tree(db=_FakeSession([]))
    assert tree == []
