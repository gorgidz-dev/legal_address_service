"""Оценка собственника не должна утечь клиенту.

Решение владельца: рейтинг внутренний. Тест сторожит именно границу — что
поля оценки нет ни в одной публичной или клиентской схеме и что ручка живёт
под /admin со staff-зависимостью.
"""
from __future__ import annotations

import app.main as main
from app.schemas.client_dashboard import ClientApplicationRead
from app.schemas.marketplace import PublicAddressRead
from app.schemas.owner_dashboard import OwnerApplicationRead

RATING_FIELDS = {"rating", "score", "provider_rating", "response", "cards", "documents"}


def _fields(model) -> set[str]:
    return set(model.model_fields)


def test_public_address_has_no_internal_rating():
    """В карточке адреса есть публичный рейтинг клиентов — но не наш внутренний."""
    leaked = _fields(PublicAddressRead) & {"provider_rating", "provider_score"}
    assert leaked == set(), leaked


def test_client_schema_has_no_rating_fields():
    assert _fields(ClientApplicationRead) & RATING_FIELDS == set()


def test_owner_schema_has_no_rating_fields():
    """Собственник свою оценку тоже не видит: это инструмент оператора."""
    assert _fields(OwnerApplicationRead) & RATING_FIELDS == set()


def test_rating_route_lives_under_admin():
    paths = [
        getattr(route, "path", "")
        for route in main.app.routes
        if "provider-ratings" in getattr(route, "path", "")
    ]
    assert paths, "маршрут оценки не зарегистрирован"
    assert all(path.startswith("/api/v1/admin/") for path in paths), paths
