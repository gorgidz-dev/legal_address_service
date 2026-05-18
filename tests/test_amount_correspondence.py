"""Расчёт суммы к оплате: почта помесячно × срок договора.

Покрывает `_compute_amount_kopeks` — сумма видна клиенту/собственнику/админу
во всех кабинетах, поэтому формула должна быть единой.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.routers.marketplace import _compute_amount_kopeks
from app.routers.payments import _compute_amount_kopeks as _payments_amount_kopeks


class _FakeDB:
    """Минимальный фейк AsyncSession: только `await db.get(...)`."""

    def __init__(self, address):
        self._address = address

    async def get(self, _model, _pk):
        return self._address


def _address(*, p6: str, p11: str, corr: str | None):
    return SimpleNamespace(
        price_6m=Decimal(p6),
        price_11m=Decimal(p11),
        correspondence_price=Decimal(corr) if corr is not None else None,
    )


def _application(*, term: int, corr: bool):
    return SimpleNamespace(term_months=term, has_correspondence_service=corr)


def test_amount_term_11_no_correspondence() -> None:
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = _application(term=11, corr=False)
    assert _compute_amount_kopeks(addr, app_) == 46000_00


def test_amount_term_6_no_correspondence() -> None:
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = _application(term=6, corr=False)
    assert _compute_amount_kopeks(addr, app_) == 28000_00


def test_amount_term_11_with_correspondence_multiplies_by_term() -> None:
    # почта 5000/мес × 11 = 55000, плюс база 46000 → 101000
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = _application(term=11, corr=True)
    assert _compute_amount_kopeks(addr, app_) == 101000_00


def test_amount_term_6_with_correspondence_multiplies_by_term() -> None:
    # почта 5000/мес × 6 = 30000, плюс база 28000 → 58000
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = _application(term=6, corr=True)
    assert _compute_amount_kopeks(addr, app_) == 58000_00


def test_amount_correspondence_flag_ignored_when_address_has_no_price() -> None:
    addr = _address(p6="28000", p11="46000", corr=None)
    app_ = _application(term=11, corr=True)
    assert _compute_amount_kopeks(addr, app_) == 46000_00


def test_amount_term_defaults_to_11_when_missing() -> None:
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = SimpleNamespace(term_months=None, has_correspondence_service=False)
    assert _compute_amount_kopeks(addr, app_) == 46000_00


# --- payments.py: формула при создании платежа (клиент/собственник/админ) ---


@pytest.mark.asyncio
async def test_payments_amount_matches_marketplace_with_correspondence() -> None:
    """payments.py и marketplace.py должны давать одну сумму."""
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = SimpleNamespace(
        address_id="x", term_months=11, has_correspondence_service=True
    )
    kopeks = await _payments_amount_kopeks(_FakeDB(addr), app_)
    assert kopeks == 101000_00
    assert kopeks == _compute_amount_kopeks(addr, app_)


@pytest.mark.asyncio
async def test_payments_amount_term_6_with_correspondence() -> None:
    addr = _address(p6="28000", p11="46000", corr="5000")
    app_ = SimpleNamespace(
        address_id="x", term_months=6, has_correspondence_service=True
    )
    assert await _payments_amount_kopeks(_FakeDB(addr), app_) == 58000_00
