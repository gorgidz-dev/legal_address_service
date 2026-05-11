from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.enums import ApplicationType, GuaranteeVariant
from app.services.document_context import (
    add_months_minus_one_day,
    build_contract_context,
    build_guarantee_context,
    format_date_ru,
    format_money,
    money_in_words,
)


def test_format_date_ru_uses_legal_document_style() -> None:
    assert format_date_ru(date(2026, 5, 8)) == "«08» мая 2026 г."


def test_add_months_minus_one_day_handles_short_and_long_terms() -> None:
    assert add_months_minus_one_day(date(2026, 5, 8), 6) == date(2026, 11, 7)
    assert add_months_minus_one_day(date(2026, 5, 8), 11) == date(2027, 4, 7)


def test_money_helpers_are_template_ready() -> None:
    assert format_money(25000) == "25 000"
    assert money_in_words(25000) == "двадцать пять тысяч"


def test_initial_guarantee_context_uses_planned_company_name_and_address_defaults() -> None:
    application = SimpleNamespace(
        type=ApplicationType.INITIAL_REGISTRATION,
        planned_client_name="Альфа",
        fns_number=None,
        fns_city=None,
    )
    provider = SimpleNamespace(
        full_name="Индивидуальный предприниматель Иванов Иван Иванович",
        inn="503809113832",
        ogrn="304770001734651",
        legal_address="123456, г. Москва, ул. Тверская, д. 1",
        phone="+74951234567",
        signatory_initials="Иванов И. И.",
    )
    address = SimpleNamespace(
        full_address="123456, г. Москва, ул. Тверская, д. 1, помещение № 5",
        cadastral_number="77:01:0001001:1234",
        ownership_doc_short="Выписки из ЕГРН",
        ownership_doc_pages=3,
        fns_number=46,
        fns_city="Москве",
    )

    context = build_guarantee_context(
        application=application,
        provider=provider,
        address=address,
        client=None,
        variant=GuaranteeVariant.INITIAL,
        guarantee_number="ГП-2026-0001",
        guarantee_date=date(2026, 5, 8),
        contract_number=None,
        contract_date=None,
    )

    assert context["client_planned_name"] == "Альфа"
    assert context["fns_number"] == 46
    assert context["fns_city"] == "Москве"
    assert context["guarantee_date_ru"] == "«08» мая 2026 г."
    assert context["provider_signatory_initials"] == "Иванов И. И."


def _minimal_contract_args(*, has_correspondence: bool, correspondence_price: Decimal | None):
    application = SimpleNamespace(
        term_months=11,
        contract_city="Москва",
        notice_period="1m",
        has_correspondence_service=has_correspondence,
    )
    provider = SimpleNamespace(
        full_name="ООО «Эталон»",
        inn="7700000001",
        kpp="770001001",
        ogrn="1027700000001",
        legal_address="г. Москва, ул. Образцовая, д. 1",
        signatory_initials="И.И. Иванов",
    )
    address = SimpleNamespace(
        full_address="г. Москва, ул. Тверская, д. 7",
        cadastral_number="77:01:0001001:0001",
        ownership_doc_short="Свидетельство",
        ownership_doc_pages=2,
        correspondence_price=correspondence_price,
    )
    client = SimpleNamespace(
        full_name="ООО «Альфа»",
        short_name="ООО «Альфа»",
        inn="7700000002",
        kpp="770001002",
        ogrn="1027700000002",
        legal_address="г. Москва, ул. Примерная, д. 2",
        signatory_position="Генеральный директор",
        signatory_name="Петров Пётр Петрович",
        signatory_initials="П.П. Петров",
    )
    return dict(
        application=application,
        provider=provider,
        address=address,
        client=client,
        contract_number="ДА-2026-0001",
        contract_date=date(2026, 1, 15),
        start_date=date(2026, 1, 15),
        price_total=Decimal("33500"),
    )


def test_contract_context_emits_correspondence_amount_when_paid() -> None:
    ctx = build_contract_context(
        **_minimal_contract_args(has_correspondence=True, correspondence_price=Decimal("3500")),
    )
    assert ctx["has_correspondence_service"] is True
    assert ctx["correspondence_price_formatted"] == "3 500"
    assert ctx["correspondence_price_in_words"] == "три тысячи пятьсот"


def test_contract_context_skips_correspondence_when_not_paid() -> None:
    ctx = build_contract_context(
        **_minimal_contract_args(has_correspondence=False, correspondence_price=Decimal("3500")),
    )
    assert ctx["has_correspondence_service"] is False
    assert ctx["correspondence_price_formatted"] == ""
    assert ctx["correspondence_price_in_words"] == ""


def test_contract_context_skips_correspondence_when_address_has_no_price() -> None:
    ctx = build_contract_context(
        **_minimal_contract_args(has_correspondence=True, correspondence_price=None),
    )
    assert ctx["correspondence_price_formatted"] == ""
    assert ctx["correspondence_price_in_words"] == ""
