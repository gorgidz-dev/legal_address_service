"""add contract_expiring application event kind

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_KIND_VALUES_OLD = (
    "created",
    "status_changed",
    "comment_added",
    "document_uploaded",
    "document_approved",
    "correction_requested",
    "dispute_opened",
    "cancelled",
)

_KIND_VALUES_NEW = _KIND_VALUES_OLD + ("contract_expiring",)


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_application_events_kind_valid"), "application_events", type_="check")
    op.create_check_constraint(
        op.f("ck_application_events_kind_valid"),
        "application_events",
        f"kind IN ({_quoted(_KIND_VALUES_NEW)})",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_application_events_kind_valid"), "application_events", type_="check")
    op.create_check_constraint(
        op.f("ck_application_events_kind_valid"),
        "application_events",
        f"kind IN ({_quoted(_KIND_VALUES_OLD)})",
    )
