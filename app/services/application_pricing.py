"""Состав суммы к оплате по заявке.

Формула была одна и жила внутри роутера платежей (`_compute_amount_kopeks`).
Пока её видел только счёт, этого хватало. Но клиент просил показать, из чего
складывается цена, — а витрина, считающая ту же сумму по своей копии формулы,
рано или поздно разойдётся со счётом на копейку или на срок. Поэтому формула
переехала сюда, и оба места зовут её.

Что в сумму НЕ входит: дополнительные услуги адреса (`address_services`).
В карточке они помечены «Подключаются после оформления заявки» и через этот
счёт не проходят — включать их в разбивку значило бы показать клиенту сумму,
которой нет в счёте.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Срок по умолчанию, если в заявке он не проставлен. Совпадает с прежним
#: поведением `_compute_amount_kopeks`.
DEFAULT_TERM_MONTHS = 11


@dataclass(frozen=True)
class PriceLine:
    """Строка разбивки: за что и сколько."""

    kind: str
    label: str
    amount: Decimal


@dataclass(frozen=True)
class PriceBreakdown:
    lines: tuple[PriceLine, ...]
    total: Decimal

    def to_kopeks(self) -> int:
        return int((self.total * 100).quantize(Decimal("1")))


def build_price_breakdown(
    *,
    term_months: int | None,
    price_6m: Decimal,
    price_11m: Decimal,
    correspondence_price: Decimal | None,
    has_correspondence_service: bool,
) -> PriceBreakdown:
    """Разбивка суммы по заявке.

    Корреспонденция тарифицируется помесячно и оплачивается сразу за весь срок
    договора — так же, как в витрине каталога.
    """
    term = term_months or DEFAULT_TERM_MONTHS
    base = price_6m if term == 6 else price_11m

    lines = [
        PriceLine(
            kind="rent",
            label=f"Аренда адреса, {term} мес.",
            amount=base,
        )
    ]
    total = base

    if has_correspondence_service and correspondence_price is not None:
        amount = correspondence_price * term
        lines.append(
            PriceLine(
                kind="correspondence",
                label=f"Приём корреспонденции, {term} мес.",
                amount=amount,
            )
        )
        total += amount

    return PriceBreakdown(lines=tuple(lines), total=total)
