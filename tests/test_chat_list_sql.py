"""Сортировка списка веток компилируется в валидный Postgres.

Раздел «Чаты» отвечал 500 на любой запрос: `desc(col.nullslast())` даёт
«ORDER BY last_message_at NULLS LAST DESC», а Postgres такого не принимает —
направление должно идти перед обработкой NULL. Ни один тест этого не видел:
все они работают на подставных сессиях, где SQL не компилируется вовсе.
Нашлось смоук-прогоном на настоящей базе 01.08.2026.

Тест дешёвый и не требует БД: компилируем выражение диалектом postgresql и
смотрим на текст.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.routers.address_chats import CHAT_LIST_ORDER


def _sql(expression) -> str:
    return str(expression.compile(dialect=postgresql.dialect()))


def test_direction_goes_before_null_handling():
    assert _sql(CHAT_LIST_ORDER[0]) == "address_chats.last_message_at DESC NULLS LAST"


def test_ties_are_broken_by_creation_time():
    assert _sql(CHAT_LIST_ORDER[1]) == "address_chats.created_at DESC"


def test_no_clause_puts_nulls_before_the_direction():
    """Общая проверка на случай, если в порядок добавят третье выражение."""
    for expression in CHAT_LIST_ORDER:
        sql = _sql(expression)
        assert "NULLS LAST DESC" not in sql, sql
        assert "NULLS FIRST DESC" not in sql, sql
        assert "NULLS LAST ASC" not in sql, sql
        assert "NULLS FIRST ASC" not in sql, sql
