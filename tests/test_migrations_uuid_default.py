"""Новая таблица не должна создаваться без умолчания для первичного ключа.

Появился после находки 01.08.2026. Первичный ключ генерирует база
(UUIDPKMixin.server_default=gen_random_uuid()), но три миграции подряд —
0030, 0031, 0032 — объявили `id` без этого умолчания. Тесты этого не заметили:
они работают на подставных сессиях и до настоящей вставки не доходят. Ошибка
всплыла только на смоук-прогоне: NotNullViolation при первой же записи.

Проверка статическая, по исходникам миграций: разбираем `op.create_table` и
требуем `server_default` у uuid-колонки `id`. Схему тем самым не проверяем —
её чинит миграция 0033, — но повтор той же ошибки поймаем до выката.
"""
from __future__ import annotations

import ast
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: Таблицы, созданные без умолчания и починенные миграцией 0033. Историю
#: переписать нельзя, поэтому исключения перечислены явно и не растут.
FIXED_BY_0033 = {
    "address_documents",
    "owner_tasks",
    "chat_message_attachments",
    "chat_reads",
}


def _is_call_to(node: ast.AST, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    )


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _upgrade_body(tree: ast.Module) -> list[ast.stmt]:
    """Только upgrade(): downgrade иногда воссоздаёт таблицы, которых уже нет
    в модели (например, 0028 откатывает удаление генератора документов), и
    придираться к их умолчаниям смысла нет."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node.body
    return []


def _uuid_id_columns_without_default(tree: ast.Module) -> list[str]:
    """Имена таблиц, чья uuid-колонка id создана без server_default."""
    bad: list[str] = []
    for statement in _upgrade_body(tree):
        for node in ast.walk(statement):
            if not _is_call_to(node, "create_table") or not node.args:
                continue
            table = _literal(node.args[0])
            if table is None:
                continue
            for arg in node.args[1:]:
                if not _is_call_to(arg, "Column") or not arg.args:
                    continue
                if _literal(arg.args[0]) != "id":
                    continue
                # Тип берём текстом: PgUUID(as_uuid=True) и sa.UUID() пишутся по-разному.
                type_src = ast.dump(arg.args[1]) if len(arg.args) > 1 else ""
                if "UUID" not in type_src:
                    continue
                if not any(kw.arg == "server_default" for kw in arg.keywords):
                    bad.append(table)
    return bad


def test_every_new_table_generates_its_own_uuid_key():
    offenders: list[tuple[str, str]] = []
    for path in sorted(VERSIONS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for table in _uuid_id_columns_without_default(tree):
            if table in FIXED_BY_0033:
                continue
            offenders.append((path.name, table))

    assert offenders == [], (
        "таблицы созданы без server_default для id — первая же вставка упадёт "
        f"NotNullViolation: {offenders}. Добавьте "
        "server_default=sa.text('gen_random_uuid()')"
    )


def test_the_known_offenders_are_actually_repaired():
    """Список исключений не должен пережить миграцию, которая их чинит."""
    fix = VERSIONS / "2026_08_01_0200_0033_uuid_pk_defaults.py"
    assert fix.exists(), "миграция 0033 пропала, а исключения в тесте остались"
    source = fix.read_text(encoding="utf-8")
    for table in FIXED_BY_0033:
        assert table in source, f"{table} числится починенной, но в 0033 её нет"
