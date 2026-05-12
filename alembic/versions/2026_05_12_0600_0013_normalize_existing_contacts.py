"""normalize legacy contact data: phones to E.164, emails to lowercase, names trimmed

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-12

Stage 9 added typed contact fields on the API surface (Pydantic Annotated[]).
Existing rows in the DB still carry the unnormalised values that were saved
before that change. This migration brings the stored data in line.

Strategy:
- Self-contained normalisers (no app import) so the migration replays cleanly.
- Per-row: if value can be normalised AND target is free (for unique columns
  like users.email), update. Otherwise skip and log via Alembic.
- Transactional: the whole pass runs inside Alembic's enclosing transaction;
  downgrade is a no-op because we can't reconstruct the original formatting.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Sequence, Union

from alembic import op


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


log = logging.getLogger("alembic.runtime.migration")

_PHONE_DIGITS_RE = re.compile(r"\d")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_WHITESPACE_RE = re.compile(r"\s+")


def _norm_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    had_plus = stripped.lstrip().startswith("+")
    digits = "".join(_PHONE_DIGITS_RE.findall(stripped))
    if not digits:
        return None
    if not had_plus:
        if len(digits) == 10:
            digits = "7" + digits
        elif len(digits) == 11 and digits[0] == "8":
            digits = "7" + digits[1:]
        elif len(digits) == 11 and digits[0] == "7":
            pass
        else:
            return None
    if not (8 <= len(digits) <= 15) or digits[0] == "0":
        return None
    return "+" + digits


def _norm_email(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    stripped = raw.strip().lower()
    if not stripped or len(stripped) > 254 or not _EMAIL_RE.match(stripped):
        return None
    return stripped


def _norm_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", raw.strip())
    if not collapsed or len(collapsed) < 2 or len(collapsed) > 200:
        return None
    return collapsed


def _update_simple(conn, table: str, column: str, normalizer) -> None:
    """Normalize a non-unique column; rows that fail normalisation are skipped."""
    rows = conn.execute(_text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")).all()
    changed = 0
    skipped = 0
    for row in rows:
        original = row[1]
        normalized = normalizer(original)
        if normalized is None:
            skipped += 1
            continue
        if normalized == original:
            continue
        conn.execute(
            _text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
            {"v": normalized, "id": row[0]},
        )
        changed += 1
    log.info("0013: %s.%s — updated %d, skipped %d", table, column, changed, skipped)


def _update_unique_email(conn, table: str, column: str) -> None:
    """Same as _update_simple but skips collisions on the unique column."""
    rows = conn.execute(_text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")).all()
    changed = 0
    skipped = 0
    collisions = 0
    seen_target: set[str] = set()
    # Pre-collect existing normalized values so we don't collide with rows
    # we leave alone.
    for row in rows:
        normalized = _norm_email(row[1])
        if normalized:
            seen_target.add(normalized)

    for row in rows:
        original = row[1]
        normalized = _norm_email(original)
        if normalized is None:
            skipped += 1
            continue
        if normalized == original:
            continue
        # Collision check against other rows with the same target value.
        clash = conn.execute(
            _text(
                f"SELECT 1 FROM {table} "
                f"WHERE {column} = :v AND id <> :id LIMIT 1"
            ),
            {"v": normalized, "id": row[0]},
        ).first()
        if clash is not None:
            collisions += 1
            log.warning(
                "0013: %s.id=%s skipped (lowercased '%s' clashes with existing row)",
                table, row[0], normalized,
            )
            continue
        conn.execute(
            _text(f"UPDATE {table} SET {column} = :v WHERE id = :id"),
            {"v": normalized, "id": row[0]},
        )
        changed += 1
    log.info(
        "0013: %s.%s — updated %d, skipped %d, collisions %d",
        table, column, changed, skipped, collisions,
    )


def _text(sql: str):
    import sqlalchemy as sa
    return sa.text(sql)


def upgrade() -> None:
    conn = op.get_bind()

    _update_unique_email(conn, "users", "email")
    _update_simple(conn, "users", "full_name", _norm_name)

    _update_simple(conn, "providers", "phone", _norm_phone)

    _update_simple(conn, "clients", "full_name", _norm_name)
    _update_simple(conn, "clients", "email", _norm_email)
    _update_simple(conn, "clients", "phone", _norm_phone)

    _update_simple(conn, "applications", "contact_name", _norm_name)
    _update_simple(conn, "applications", "contact_email", _norm_email)
    _update_simple(conn, "applications", "contact_phone", _norm_phone)

    _update_simple(conn, "invitations", "email", _norm_email)
    _update_simple(conn, "invitations", "full_name", _norm_name)

    _update_simple(conn, "provider_connection_requests", "contact_name", _norm_name)
    _update_simple(conn, "provider_connection_requests", "contact_email", _norm_email)
    _update_simple(conn, "provider_connection_requests", "contact_phone", _norm_phone)


def downgrade() -> None:
    # Data normalisation is one-way; the pre-cleanup raw values are not
    # reconstructable. Leave the table contents alone on downgrade.
    pass
