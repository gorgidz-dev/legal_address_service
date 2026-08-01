"""Маршруты действительно зарегистрированы и ведут в свои функции.

Появился после боевой поломки 30.07.2026: при правке client_dashboard хелпер
вставился между `@router.get` и функцией эндпоинта, декоратор навесился на
хелпер, и `/client/applications` перестал существовать в прежнем виде. Ни один
тест этого не заметил — все они зовут функции напрямую, минуя HTTP-слой.

Здесь проверяется именно то, что тот случай пропустил: путь есть в приложении
и за ним стоит функция с ожидаемым именем.
"""
from __future__ import annotations

import pytest

import app.main as main

#: (метод, путь) → имя функции-обработчика. Ключ с методом, а не один путь:
#: на /applications висят и GET, и POST. Список не исчерпывающий — сюда
#: добавляются маршруты, поломка которых незаметна для остальных тестов.
EXPECTED = {
    ("GET", "/api/v1/client/applications"): "list_client_applications",
    ("GET", "/api/v1/client/lease-calendar"): "client_lease_calendar",
    ("GET", "/api/v1/owner/dashboard"): "get_owner_dashboard",
    ("GET", "/api/v1/owner/lease-calendar"): "owner_lease_calendar",
    ("GET", "/api/v1/applications"): "list_applications",
    ("POST", "/api/v1/applications"): "create_application",
    ("GET", "/api/v1/registry/active-clients"): "active_clients_registry",
    ("GET", "/api/v1/owner/tasks"): "my_tasks",
    ("POST", "/api/v1/admin/owner-tasks"): "create",
    ("GET", "/api/v1/owner/address-stats"): "owner_address_stats",
    ("GET", "/api/v1/owner/addresses/{address_id}/documents"): "list_documents",
}


def _routes() -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for route in main.app.routes:
        if not (hasattr(route, "endpoint") and hasattr(route, "path")):
            continue
        for method in getattr(route, "methods", None) or []:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found[(method, route.path)] = route.endpoint.__name__
    return found


@pytest.mark.parametrize(("key", "handler"), sorted(EXPECTED.items()))
def test_route_points_at_its_own_handler(key, handler):
    routes = _routes()
    assert key in routes, f"маршрут {key[0]} {key[1]} не зарегистрирован"
    assert routes[key] == handler, (
        f"{key[0]} {key[1]} ведёт в {routes[key]!r}, а должен в {handler!r} — "
        "вероятно, декоратор навесился не на ту функцию"
    )


def test_no_private_helper_is_exposed_as_endpoint():
    """Функция с подчёркиванием в начале имени не должна быть обработчиком."""
    exposed = [
        (key, name)
        for key, name in _routes().items()
        if name.startswith("_")
    ]
    assert exposed == [], f"приватные функции торчат наружу: {exposed}"
