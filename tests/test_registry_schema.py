from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.schemas.registry import ActiveClientRegistryItem, renewal_state


def test_renewal_state_marks_overdue_soon_and_active() -> None:
    today = date(2026, 5, 8)

    assert renewal_state(date(2026, 5, 7), today=today) == "overdue"
    assert renewal_state(date(2026, 5, 20), today=today) == "due_soon"
    assert renewal_state(date(2026, 7, 1), today=today) == "active"


def test_active_client_registry_item_contains_client_contract_and_contacts() -> None:
    item = ActiveClientRegistryItem(
        application_id=uuid4(),
        contract_id=uuid4(),
        client_id=uuid4(),
        company_name='ООО "ИНТЕРНЕТ РЕШЕНИЯ"',
        client_inn="7704217370",
        contact_name="Ирина Ковалёва",
        contact_phone="+7 925 747-11-03",
        contact_email="office@example.ru",
        provider_name="ИП Иванов И. И.",
        address_full="г. Москва, ул. Тверская, д. 1",
        contract_number="ДА-2026-0001",
        contract_date=date(2026, 5, 8),
        start_date=date(2026, 5, 8),
        end_date=date(2027, 4, 7),
        renewal_date=date(2027, 4, 7),
        term_months=11,
        days_until_renewal=334,
        price_total=Decimal("25000.00"),
        renewal_status="active",
    )

    assert item.company_name == 'ООО "ИНТЕРНЕТ РЕШЕНИЯ"'
    assert item.contact_phone == "+7 925 747-11-03"
    assert item.contract_number == "ДА-2026-0001"
