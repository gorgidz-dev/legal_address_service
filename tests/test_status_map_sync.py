"""Список статусов заявки продублирован на фронте — здесь он сверяется с enum.

Копий три: app/enums.py (источник), frontend/src/types.ts (union-тип) и карта
подписей frontend/src/status.ts. Внутри фронта пропуск ловит компилятор —
карта объявлена как Record<ApplicationStatus, StatusMeta>. А вот расхождение
между Python и TypeScript не видит ни pytest, ни tsc: новый статус на бэкенде
доезжает до интерфейса сырым кодом вроде «partial_refund».
"""

from __future__ import annotations

import re
from pathlib import Path

from app.enums import ApplicationStatus

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"


def _typescript_union_values(source: str, type_name: str) -> set[str]:
    """Значения строкового union-типа: `export type X = "a" | "b";`"""
    match = re.search(rf"export type {type_name} =(.+?);", source, re.DOTALL)
    assert match, f"union-тип {type_name} не найден"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _status_map_keys(source: str) -> set[str]:
    """Ключи карты STATUS до закрывающей скобки объявления."""
    match = re.search(
        r"export const STATUS: Record<ApplicationStatus, StatusMeta> = \{(.+?)\n\};",
        source,
        re.DOTALL,
    )
    assert match, "карта STATUS не найдена"
    return set(re.findall(r"^\s{2}(\w+):", match.group(1), re.MULTILINE))


def test_frontend_union_matches_backend_enum() -> None:
    values = _typescript_union_values(
        (FRONTEND / "types.ts").read_text(encoding="utf-8"), "ApplicationStatus"
    )
    assert values == {status.value for status in ApplicationStatus}


def test_status_map_covers_every_backend_status() -> None:
    keys = _status_map_keys((FRONTEND / "status.ts").read_text(encoding="utf-8"))
    assert keys == {status.value for status in ApplicationStatus}


def test_short_labels_fit_the_table_cell() -> None:
    """Ячейка «Статус» в очереди — 124px; длинная подпись обрежется многоточием
    и перестанет читаться, поэтому короткие варианты ограничены по длине."""
    source = (FRONTEND / "status.ts").read_text(encoding="utf-8")
    shorts = re.findall(r'short: "([^"]+)"', source)
    assert shorts, "короткие подписи не найдены"
    too_long = [value for value in shorts if len(value) > 14]
    assert not too_long, f"короткие подписи длиннее 14 символов: {too_long}"
