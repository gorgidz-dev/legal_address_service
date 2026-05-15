"""addresses_fts — tsvector + GIN-индекс для поиска по адресам.

Зачем: до этого поиск в публичном каталоге шёл клиентом по уже загруженному
массиву. При росте каталога > 100 адресов это ляжет. Делаем серверный FTS:
PostgreSQL tsvector(russian) с нормализацией ё→е, GIN-индекс.

Стратегия:
- Generated column `search_tsv`, auto-maintained самой PG (без триггеров).
- Нормализация в выражении: lower() + replace('ё','е'). Этого достаточно,
  чтобы запрос "артем" находил "Артём" — а stemming russian-config'а
  уже сам схлопнёт "тверская/тверской/тверскую".
- Без unaccent-расширения: нам нужна только ё/е, не латинские диакритики.
- В FTS попадают full_address + fns_city + fns_number::text. Provider name
  не включаем — клиенты по нему ищут редко, а денормализация требует триггера
  на обновления Provider.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Generated column: PostgreSQL поддерживает GENERATED ALWAYS AS ... STORED
    # с 12-й версии. У нас 14+.
    op.execute(
        """
        ALTER TABLE addresses
        ADD COLUMN search_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'russian',
                replace(
                    lower(
                        coalesce(full_address, '') || ' ' ||
                        coalesce(fns_city, '') || ' ' ||
                        coalesce(fns_number::text, '')
                    ),
                    'ё', 'е'
                )
            )
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX ix_addresses_search_tsv ON addresses USING GIN(search_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_addresses_search_tsv")
    op.execute("ALTER TABLE addresses DROP COLUMN IF EXISTS search_tsv")
