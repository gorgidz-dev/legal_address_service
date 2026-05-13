"""address_services.kind — расширить каталог 5 платными доп.услугами.

Добавляем: door_sign, mail_reception, fns_visit_photo, phone_answering,
visitor_reception. Цены и активность задаёт админ/собственник в кабинете.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_CHECK = (
    "kind IN ("
    "'guarantee_letter', 'lease_agreement', 'owner_confirmation',"
    " 'door_sign', 'mail_reception', 'fns_visit_photo',"
    " 'phone_answering', 'visitor_reception'"
    ")"
)
OLD_CHECK = (
    "kind IN ('guarantee_letter', 'lease_agreement', 'owner_confirmation')"
)


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_address_services_address_services_kind_valid"),
        "address_services",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_address_services_address_services_kind_valid"),
        "address_services",
        NEW_CHECK,
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM address_services WHERE kind NOT IN ("
        "'guarantee_letter', 'lease_agreement', 'owner_confirmation')"
    )
    op.drop_constraint(
        op.f("ck_address_services_address_services_kind_valid"),
        "address_services",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_address_services_address_services_kind_valid"),
        "address_services",
        OLD_CHECK,
    )
