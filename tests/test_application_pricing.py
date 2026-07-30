"""Разбивка стоимости заявки.

Главное, что здесь проверяется, — не арифметика сама по себе, а то, что сумма
строк разбивки равна итогу, который уходит в счёт. Разойдись они — клиент
увидел бы «за что» одно, а к оплате другое.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.application_pricing import DEFAULT_TERM_MONTHS, build_price_breakdown

BASE_6M = Decimal("18000")
BASE_11M = Decimal("30000")
CORR = Decimal("3000")


def _breakdown(*, term=11, corr=True, corr_price=CORR):
    return build_price_breakdown(
        term_months=term,
        price_6m=BASE_6M,
        price_11m=BASE_11M,
        correspondence_price=corr_price,
        has_correspondence_service=corr,
    )


def test_lines_sum_to_total():
    """Инвариант: разбивка сходится с итогом."""
    result = _breakdown()
    assert sum((line.amount for line in result.lines), Decimal("0")) == result.total


def test_without_correspondence_only_rent_line():
    result = _breakdown(corr=False)
    assert [line.kind for line in result.lines] == ["rent"]
    assert result.total == BASE_11M


def test_correspondence_is_charged_for_whole_term():
    """Почта помесячная, но платится сразу за весь срок."""
    result = _breakdown(term=11)
    corr_line = next(line for line in result.lines if line.kind == "correspondence")
    assert corr_line.amount == CORR * 11
    assert result.total == BASE_11M + CORR * 11


def test_six_month_term_uses_six_month_price():
    result = _breakdown(term=6)
    rent = next(line for line in result.lines if line.kind == "rent")
    assert rent.amount == BASE_6M
    assert result.total == BASE_6M + CORR * 6


def test_term_appears_in_labels():
    """Клиент должен видеть, за какой срок с него берут."""
    result = _breakdown(term=6)
    assert all("6 мес." in line.label for line in result.lines)


def test_missing_term_falls_back_to_default():
    assert _breakdown(term=None).total == _breakdown(term=DEFAULT_TERM_MONTHS).total


def test_correspondence_flag_without_price_adds_nothing():
    """Услуга включена, а цена у адреса не задана — строки быть не должно."""
    result = _breakdown(corr=True, corr_price=None)
    assert [line.kind for line in result.lines] == ["rent"]


@pytest.mark.parametrize("term", [6, 11])
def test_kopeks_match_total(term):
    """Счёт берёт копейки из того же объекта — округление одно на двоих."""
    result = _breakdown(term=term)
    assert result.to_kopeks() == int(result.total * 100)


def test_services_are_not_included():
    """Доп. услуги адреса через этот счёт не проходят — их в разбивке нет."""
    kinds = {line.kind for line in _breakdown().lines}
    assert kinds <= {"rent", "correspondence"}
