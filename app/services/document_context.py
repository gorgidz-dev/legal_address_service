from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pytils import numeral

from app.enums import GuaranteeVariant

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
