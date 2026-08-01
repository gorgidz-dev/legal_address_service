"""nginx проксирует ровно тот путь WebSocket, который поднимает приложение.

Апгрейд был настроен на `/ws/`, а приложение монтирует сокет по
`/api/v1/ws/chats/{id}` — тот попадал в общий блок `/api/` без заголовков
Upgrade/Connection, рукопожатие не происходило, и браузер получал обрыв 1006.
Чат при этом выглядел работающим: история грузилась, отправка проходила, не
было только живой доставки — то есть единственного, ради чего сокет и нужен.

Тест сверяет маршруты приложения с конфигом: для каждого websocket-пути
находит блок, который выберет nginx (самый длинный совпадающий префикс), и
требует в нём Upgrade. Заодно ловит обратное — «мёртвый» блок с апгрейдом,
который ничему в приложении не соответствует.
"""
from __future__ import annotations

import re
from pathlib import Path

from starlette.routing import WebSocketRoute

import app.main as main

NGINX = Path(__file__).resolve().parents[1] / "frontend" / "nginx.conf"

LOCATION = re.compile(r"^\s*location\s+(=\s*)?(?P<path>/\S*)\s*\{", re.MULTILINE)


def _prefix_blocks() -> dict[str, str]:
    """Префиксные location-блоки конфига: путь → тело."""
    source = NGINX.read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for match in LOCATION.finditer(source):
        path = match.group("path")
        start = source.index("{", match.start())
        depth, index = 0, start
        while index < len(source):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        blocks[path] = source[start : index + 1]
    return blocks


def _websocket_paths() -> list[str]:
    return [
        route.path
        for route in main.app.routes
        if isinstance(route, WebSocketRoute)
    ]


def _chosen_block(path: str, blocks: dict[str, str]) -> tuple[str, str] | None:
    """Блок, который выберет nginx: самый длинный подходящий префикс."""
    candidates = [(p, body) for p, body in blocks.items() if path.startswith(p)]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item[0]))


def test_application_actually_has_a_websocket():
    assert _websocket_paths(), "websocket-маршрутов нет — тест потерял смысл"


def test_nginx_upgrades_every_websocket_path():
    blocks = _prefix_blocks()
    for path in _websocket_paths():
        # Шаблонный сегмент вида {chat_id} на выбор location не влияет.
        concrete = path.replace("{chat_id}", "00000000")
        chosen = _chosen_block(concrete, blocks)
        assert chosen is not None, f"{path}: в nginx нет подходящего location"
        location, body = chosen
        assert "proxy_set_header Upgrade" in body, (
            f"{path} попадёт в location {location}, а там нет Upgrade — "
            "рукопожатие не состоится и браузер получит обрыв 1006"
        )
        assert "$connection_upgrade" in body, (
            f"{path}: в location {location} нет Connection: upgrade"
        )


def test_no_upgrade_block_points_at_nothing():
    """Блок с апгрейдом, которому нечего проксировать, — забытый конфиг."""
    paths = [p.replace("{chat_id}", "00000000") for p in _websocket_paths()]
    dead = [
        location
        for location, body in _prefix_blocks().items()
        if "proxy_set_header Upgrade" in body
        and not any(path.startswith(location) for path in paths)
    ]
    assert dead == [], f"апгрейд настроен на пути, которых нет в приложении: {dead}"
