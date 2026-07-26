"""Подтверждение e-mail при самостоятельной регистрации.

Публичная форма заявки создавала аккаунт на любой введённый адрес: опечатка
означала потерянный доступ и уведомления в никуда, а чужой адрес позволял
занять его владельца.

Существующим пользователям ставим email_verified_at = created_at: они пришли
по приглашению админа либо были заведены вручную, то есть адрес уже
подтверждён другим путём. Требовать от них повторного подтверждения задним
числом — значит без причины сломать работающие аккаунты.

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_token_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email_verification_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Поиск по токену идёт на публичном эндпоинте подтверждения.
    op.create_index(
        "ix_users_email_verification_token_hash",
        "users",
        ["email_verification_token_hash"],
        unique=False,
        postgresql_where=sa.text("email_verification_token_hash IS NOT NULL"),
    )
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")


def downgrade() -> None:
    op.drop_index("ix_users_email_verification_token_hash", table_name="users")
    op.drop_column("users", "email_verification_sent_at")
    op.drop_column("users", "email_verification_token_hash")
    op.drop_column("users", "email_verified_at")
