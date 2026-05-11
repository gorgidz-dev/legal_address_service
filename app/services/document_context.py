from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from pytils import numeral

from app.enums import GuaranteeVariant, TemplateKind

MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_date_ru(value: date, *, quote_day: bool = True) -> str:
    day = f"{value.day:02d}"
    if quote_day:
        day = f"«{day}»"
    return f"{day} {MONTHS_GENITIVE[value.month]} {value.year} г."


def add_months_minus_one_day(start_date: date, months: int) -> date:
    target_month_index = start_date.month - 1 + months
    year = start_date.year + target_month_index // 12
    month = target_month_index % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day) - timedelta(days=1)


def format_money(value: Decimal | int | float | str) -> str:
    amount = Decimal(str(value)).quantize(Decimal("1"))
    return f"{int(amount):,}".replace(",", " ")


def money_in_words(value: Decimal | int | float | str) -> str:
    amount = Decimal(str(value)).quantize(Decimal("1"))
    return numeral.in_words(int(amount))


def _get(obj: Any, name: str, default: Any = None) -> Any:
    return getattr(obj, name, default)


def _provider_context(provider: Any) -> dict[str, Any]:
    return {
        "provider_full_name": _get(provider, "full_name", ""),
        "provider_inn": _get(provider, "inn", ""),
        "provider_kpp": _get(provider, "kpp", ""),
        "provider_ogrn": _get(provider, "ogrn", ""),
        "provider_legal_address": _get(provider, "legal_address", ""),
        "provider_signatory_initials": _get(provider, "signatory_initials", ""),
    }


def _address_context(address: Any) -> dict[str, Any]:
    return {
        "address_full": _get(address, "full_address", ""),
        "address_cadastral_number": _get(address, "cadastral_number", ""),
        "ownership_doc_short": _get(address, "ownership_doc_short", ""),
        "ownership_doc_pages": _get(address, "ownership_doc_pages", ""),
    }


def _client_context(client: Any) -> dict[str, Any]:
    if client is None:
        return {}
    return {
        "client_full_name": _get(client, "full_name", ""),
        "client_short_name": _get(client, "short_name", ""),
        "client_inn": _get(client, "inn", ""),
        "client_kpp": _get(client, "kpp", ""),
        "client_ogrn": _get(client, "ogrn", ""),
        "client_legal_address": _get(client, "legal_address", ""),
        "client_signatory_genitive": _get(client, "signatory_name_genitive", "")
        or " ".join(
            part for part in (
                _get(client, "signatory_position", ""),
                _get(client, "signatory_name", ""),
            )
            if part
        ),
        "client_signatory_initials": _get(client, "signatory_initials", "")
        or _get(client, "signatory_name", ""),
    }


def build_guarantee_context(
    *,
    application: Any,
    provider: Any,
    address: Any,
    client: Any,
    variant: GuaranteeVariant,
    guarantee_number: str,
    guarantee_date: date,
    contract_number: str | None,
    contract_date: date | None,
) -> dict[str, Any]:
    context = {
        **_provider_context(provider),
        **_address_context(address),
        "provider_phone": _get(provider, "phone", ""),
        "fns_number": _get(application, "fns_number") or _get(address, "fns_number", ""),
        "fns_city": _get(application, "fns_city") or _get(address, "fns_city", ""),
        "guarantee_number": guarantee_number,
        "guarantee_date_ru": format_date_ru(guarantee_date),
    }

    if variant == GuaranteeVariant.INITIAL:
        context["client_planned_name"] = _get(application, "planned_client_name", "")
    else:
        context.update(_client_context(client))
        context["contract_number"] = contract_number or ""
        context["contract_date_ru"] = format_date_ru(contract_date) if contract_date else ""

    return context


def build_contract_context(
    *,
    application: Any,
    provider: Any,
    address: Any,
    client: Any,
    contract_number: str,
    contract_date: date,
    start_date: date,
    price_total: Decimal,
) -> dict[str, Any]:
    term_months = _get(application, "term_months")
    if term_months not in (6, 11):
        raise ValueError("term_months должен быть 6 или 11")
    end_date = add_months_minus_one_day(start_date, term_months)
    has_correspondence = bool(_get(application, "has_correspondence_service", False))
    correspondence_price_raw = _get(address, "correspondence_price")
    if has_correspondence and correspondence_price_raw is not None:
        correspondence_price = Decimal(str(correspondence_price_raw))
        correspondence_price_formatted = format_money(correspondence_price)
        correspondence_price_in_words = money_in_words(correspondence_price)
    else:
        correspondence_price_formatted = ""
        correspondence_price_in_words = ""
    return {
        **_provider_context(provider),
        **_address_context(address),
        **_client_context(client),
        "contract_number": contract_number,
        "contract_date_ru": format_date_ru(contract_date),
        "contract_city": _get(application, "contract_city", "") or "",
        "start_date_ru": format_date_ru(start_date, quote_day=False),
        "end_date_ru": format_date_ru(end_date, quote_day=False),
        "term_months": term_months,
        "notice_period": _get(application, "notice_period", ""),
        "has_correspondence_service": has_correspondence,
        "correspondence_price_formatted": correspondence_price_formatted,
        "correspondence_price_in_words": correspondence_price_in_words,
        "price_total_formatted": format_money(price_total),
        "price_total_in_words": money_in_words(price_total),
    }


def _reference_provider() -> SimpleNamespace:
    return SimpleNamespace(
        full_name="ООО «Эталон Недвижимость»",
        inn="7700000001",
        kpp="770001001",
        ogrn="1027700000001",
        legal_address="г. Москва, ул. Образцовая, д. 1",
        signatory_initials="И.И. Иванов",
        phone="+7 (495) 000-00-00",
    )


def _reference_address() -> SimpleNamespace:
    return SimpleNamespace(
        full_address="г. Москва, ул. Тверская, д. 7, офис 41",
        cadastral_number="77:01:0001001:0001",
        ownership_doc_short="Свидетельство 77-АН №000000",
        ownership_doc_pages="2",
        fns_number=46,
        fns_city="Москве",
        correspondence_price=Decimal("3500"),
    )


def _reference_client() -> SimpleNamespace:
    return SimpleNamespace(
        full_name="Общество с ограниченной ответственностью «Альфа»",
        short_name="ООО «Альфа»",
        inn="7700000002",
        kpp="770001002",
        ogrn="1027700000002",
        legal_address="г. Москва, ул. Примерная, д. 2",
        signatory_position="Генеральный директор",
        signatory_name="Петров Пётр Петрович",
        signatory_name_genitive="Генерального директора Петрова Петра Петровича",
        signatory_initials="П.П. Петров",
    )


def _reference_application(*, with_client: bool) -> SimpleNamespace:
    return SimpleNamespace(
        term_months=11,
        contract_city="Москва",
        notice_period="один месяц",
        has_correspondence_service=True,
        fns_number=46,
        fns_city="Москве",
        planned_client_name="ООО «Альфа»" if not with_client else None,
    )


def build_reference_render_context(kind: TemplateKind) -> dict[str, Any]:
    """Полностью заполненный контекст для тестового рендера шаблона при загрузке.

    Идея: после upload админ должен моментально узнать, что шаблон бьётся
    с пайплайном генерации. Если переменная отсутствует или Jinja-выражение
    битое — рендер упадёт здесь, а не на боевой заявке.
    """
    today = date(2026, 1, 15)
    if kind == TemplateKind.CONTRACT:
        return build_contract_context(
            application=_reference_application(with_client=True),
            provider=_reference_provider(),
            address=_reference_address(),
            client=_reference_client(),
            contract_number="ДА-2026-0001",
            contract_date=today,
            start_date=today,
            price_total=Decimal("33500"),
        )
    if kind == TemplateKind.GUARANTEE_INITIAL:
        return build_guarantee_context(
            application=_reference_application(with_client=False),
            provider=_reference_provider(),
            address=_reference_address(),
            client=None,
            variant=GuaranteeVariant.INITIAL,
            guarantee_number="ГП-2026-0001",
            guarantee_date=today,
            contract_number=None,
            contract_date=None,
        )
    if kind == TemplateKind.GUARANTEE_FULL:
        return build_guarantee_context(
            application=_reference_application(with_client=True),
            provider=_reference_provider(),
            address=_reference_address(),
            client=_reference_client(),
            variant=GuaranteeVariant.FULL,
            guarantee_number="ГП-2026-0002",
            guarantee_date=today,
            contract_number="ДА-2026-0001",
            contract_date=today,
        )
    raise ValueError(f"Неизвестный TemplateKind: {kind}")
