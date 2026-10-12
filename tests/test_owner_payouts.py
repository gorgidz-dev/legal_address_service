"""Выплаты собственникам: деление суммы, сверка адреса, переходы статусов.

Сессия подставная — SQL здесь не проверяется; запись в настоящий Postgres
проверяет scripts/smoke_owner_payouts.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.enums import ApplicationStatus, NotificationAudience, PaymentStatus
from app.models.application_event import ApplicationEvent
from app.models.owner_payout import OwnerPayout
from app.models.provider import Provider
from app.services import owner_payouts
from app.services.owner_payouts import (
    AWAITING_REGISTRATION,
    CANCELLED,
    DUE,
    PAID,
    PayoutError,
    RegistrationCheck,
    addresses_match,
    split,
)

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
OUR_ADDRESS = "г. Москва, ул. Тверская, д. 7, стр. 1, помещ. 3"


# ------------------------------------------------------------------
# Деление суммы
# ------------------------------------------------------------------


def test_split_sums_back_to_gross_and_rounds_commission_half_up() -> None:
    assert split(3_000_000, Decimal("20")) == (600_000, 2_400_000)
    # 12.5% от 1 001 копейки = 125.125 → 125; от 1 003 = 125.375 → 125; 1 004 → 125.5 → 126
    assert split(1_001, Decimal("12.5")) == (125, 876)
    assert split(1_004, Decimal("12.5")) == (126, 878)
    for gross in (1, 999, 4_500_000, 7_777_777):
        commission, payout = split(gross, Decimal("17.35"))
        assert commission + payout == gross


def test_zero_percent_means_whole_sum_to_owner() -> None:
    assert split(4_500_000, Decimal("0")) == (0, 4_500_000)


# ------------------------------------------------------------------
# Сверка адреса с ЕГРЮЛ
# ------------------------------------------------------------------


def test_egrul_address_in_dadata_format_matches_catalog_address() -> None:
    egrul = (
        "125009, г Москва, муниципальный округ Тверской вн.тер.г., ул Тверская, "
        "д 7, стр 1, помещ. 3"
    )
    assert addresses_match(OUR_ADDRESS, egrul) is True


def test_other_house_number_does_not_match() -> None:
    assert addresses_match(OUR_ADDRESS, "125009, г Москва, ул Тверская, д 9, стр 1, помещ. 3") is False


def test_other_street_with_same_numbers_does_not_match() -> None:
    assert addresses_match(OUR_ADDRESS, "г Москва, ул Арбат, д 7, стр 1, помещ. 3") is False


def test_letters_in_room_number_are_compared() -> None:
    ours = "г. Москва, д. Марьино, ул. Жемчужная, д. 1, к. 6, помещ. 41к"
    assert addresses_match(ours, "108815, г Москва, д Марьино, ул Жемчужная, д 1, к 6, помещ. 41к") is True
    assert addresses_match(ours, "108815, г Москва, д Марьино, ул Жемчужная, д 1, к 6, помещ. 41") is False


def test_no_egrul_address_is_unknown_not_mismatch() -> None:
    assert addresses_match(OUR_ADDRESS, None) is None


# ------------------------------------------------------------------
# Подставная сессия
# ------------------------------------------------------------------


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, *, provider=None, active=None):
        self.provider = provider
        self.active = active
        self.added: list = []

    async def get(self, model, key):
        if model is Provider and self.provider is not None and self.provider.id == key:
            return self.provider
        return None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity") if hasattr(stmt, "column_descriptions") else None
        if entity is OwnerPayout:
            return _Result(self.active)
        raise RuntimeError("no subscriptions in unit tests")  # dispatch_event внутри событий

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def events(self, audience):
        return [
            e for e in self.added if isinstance(e, ApplicationEvent) and e.audience == audience.value
        ]


def _provider(percent=Decimal("20"), **kw):
    return SimpleNamespace(
        id=uuid4(), commission_percent=percent, full_name='ООО "Адрес"', inn="7700000000",
        kpp="770001001", bank_name="Банк", settlement_account="40702810000000000001",
        corr_account="30101810000000000001", bik="044525000", **kw,
    )


def _application(status=ApplicationStatus.READY_FOR_CLIENT, provider=None, **kw):
    values = dict(
        id=uuid4(), status=status.value, type="initial_registration",
        provider_id=provider.id if provider else uuid4(),
        created_at=NOW - timedelta(days=20), registration_confirmed_at=None,
        registration_inn=None, registration_check=None, registration_confirmed_by=None,
    )
    values.update(kw)
    return SimpleNamespace(**values)


def _payment(provider="tbank", status=PaymentStatus.SUCCEEDED, amount=3_000_000, **kw):
    values = dict(
        id=uuid4(), provider=provider, status=status.value, amount_kopeks=amount,
        refunded_kopeks=0, provider_status="CONFIRMED", provider_account="1700000000000",
    )
    values.update(kw)
    return SimpleNamespace(**values)


def _check(**kw):
    values = dict(
        inn="7701234567", found=True, full_name='ООО "Клиент"', ogrn="1267700000000",
        registration_date=date(2026, 10, 1), egrul_status="ACTIVE",
        legal_address="г Москва, ул Тверская, д 7, стр 1, помещ. 3", our_address=OUR_ADDRESS,
        address_matches=True,
    )
    values.update(kw)
    return RegistrationCheck(**values)


# ------------------------------------------------------------------
# Заведение выплаты при оплате
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paid_through_platform_creates_payout_with_percent_snapshot() -> None:
    provider = _provider(Decimal("20"))
    db = _DB(provider=provider)
    payout = await owner_payouts.ensure_payout(db, _application(provider=provider), _payment())
    assert payout.status == AWAITING_REGISTRATION
    assert (payout.gross_kopeks, payout.commission_kopeks, payout.payout_kopeks) == (3_000_000, 600_000, 2_400_000)
    assert payout.commission_percent == Decimal("20")


@pytest.mark.asyncio
async def test_owner_invoice_payment_creates_no_payout() -> None:
    provider = _provider()
    db = _DB(provider=provider)
    assert await owner_payouts.ensure_payout(db, _application(provider=provider), _payment("manual_invoice")) is None
    assert db.added == []


@pytest.mark.asyncio
async def test_demo_terminal_payment_creates_no_payout() -> None:
    provider = _provider()
    db = _DB(provider=provider)
    payment = _payment(provider_account="1700000000000DEMO")
    assert await owner_payouts.ensure_payout(db, _application(provider=provider), payment) is None


@pytest.mark.asyncio
async def test_existing_payout_is_returned_not_duplicated() -> None:
    provider = _provider()
    existing = SimpleNamespace(id=uuid4(), status=AWAITING_REGISTRATION)
    db = _DB(provider=provider, active=existing)
    assert await owner_payouts.ensure_payout(db, _application(provider=provider), _payment()) is existing
    assert db.added == []


@pytest.mark.asyncio
async def test_no_percent_anywhere_leaves_amounts_open(monkeypatch) -> None:
    monkeypatch.setattr(owner_payouts.settings, "owner_commission_default_percent", None)
    provider = _provider(None)
    payout = await owner_payouts.ensure_payout(_DB(provider=provider), _application(provider=provider), _payment())
    assert payout.commission_percent is None and payout.payout_kopeks is None


@pytest.mark.asyncio
async def test_default_percent_from_settings_when_owner_has_none(monkeypatch) -> None:
    monkeypatch.setattr(owner_payouts.settings, "owner_commission_default_percent", Decimal("15"))
    provider = _provider(None)
    payout = await owner_payouts.ensure_payout(_DB(provider=provider), _application(provider=provider), _payment())
    assert payout.commission_percent == Decimal("15")
    assert payout.payout_kopeks == 2_550_000


# ------------------------------------------------------------------
# Блокировки
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "app_status",
    [ApplicationStatus.DISPUTE, ApplicationStatus.REFUND_PENDING, ApplicationStatus.REFUNDED, ApplicationStatus.CANCELLED],
)
def test_money_may_go_back_blocks_payout(app_status) -> None:
    assert owner_payouts.payout_blockers(_application(app_status), _payment())


def test_refund_on_payment_blocks_payout() -> None:
    assert owner_payouts.payout_blockers(_application(), _payment(status=PaymentStatus.REFUNDED))
    assert owner_payouts.payout_blockers(_application(), _payment(refunded_kopeks=100))
    assert owner_payouts.payout_blockers(_application(), _payment(provider_status="PARTIAL_REFUNDED"))


def test_clean_paid_application_has_no_blockers() -> None:
    assert owner_payouts.payout_blockers(_application(ApplicationStatus.COMPLETED), _payment()) == []


# ------------------------------------------------------------------
# Подтверждение регистрации
# ------------------------------------------------------------------


async def _confirm(db, application, payment, check=None, accept=False):
    return await owner_payouts.confirm_registration(
        db, application=application, payment=payment, check=check or _check(),
        accept_address_mismatch=accept, admin_id=uuid4(), now=NOW,
    )


@pytest.mark.asyncio
async def test_confirm_moves_payout_to_due_and_tells_owner_the_amount() -> None:
    provider = _provider(Decimal("20"))
    db = _DB(provider=provider)
    application = _application(provider=provider)
    payout = await _confirm(db, application, _payment())
    assert payout.status == DUE and payout.due_at == NOW
    assert application.registration_confirmed_at == NOW
    assert application.registration_inn == "7701234567"
    assert application.registration_check["address_matches"] is True
    owner_events = db.events(NotificationAudience.OWNER)
    assert len(owner_events) == 1 and "24 000,00 ₽" in owner_events[0].message


@pytest.mark.asyncio
async def test_confirm_before_documents_issued_is_refused() -> None:
    provider = _provider()
    application = _application(ApplicationStatus.DOCUMENTS_PREPARING, provider=provider)
    with pytest.raises(PayoutError, match="Документы"):
        await _confirm(_DB(provider=provider), application, _payment())
    assert application.registration_confirmed_at is None


@pytest.mark.asyncio
async def test_confirm_in_dispute_is_refused() -> None:
    provider = _provider()
    with pytest.raises(PayoutError):
        await _confirm(_DB(provider=provider), _application(ApplicationStatus.DISPUTE, provider=provider), _payment())


@pytest.mark.asyncio
async def test_address_mismatch_needs_explicit_manual_check() -> None:
    provider = _provider()
    application = _application(provider=provider)
    with pytest.raises(PayoutError, match="вручную"):
        await _confirm(_DB(provider=provider), application, _payment(), _check(address_matches=False))
    payout = await _confirm(_DB(provider=provider), application, _payment(), _check(address_matches=False), accept=True)
    assert payout.status == DUE
    assert application.registration_check["accepted_address_mismatch"] is True


@pytest.mark.asyncio
async def test_company_not_found_cannot_be_confirmed_even_with_manual_flag() -> None:
    provider = _provider()
    with pytest.raises(PayoutError, match="не найдена"):
        await _confirm(
            _DB(provider=provider), _application(provider=provider), _payment(),
            _check(found=False, address_matches=None), accept=True,
        )


@pytest.mark.asyncio
async def test_owner_invoice_application_has_nothing_to_confirm() -> None:
    provider = _provider()
    with pytest.raises(PayoutError, match="напрямую"):
        await _confirm(_DB(provider=provider), _application(provider=provider), _payment("manual_invoice"))


@pytest.mark.asyncio
async def test_second_confirmation_is_refused() -> None:
    provider = _provider()
    application = _application(provider=provider, registration_confirmed_at=NOW)
    with pytest.raises(PayoutError, match="уже подтверждена"):
        await _confirm(_DB(provider=provider), application, _payment())


@pytest.mark.asyncio
async def test_confirm_without_any_percent_is_refused_before_touching_application(monkeypatch) -> None:
    monkeypatch.setattr(owner_payouts.settings, "owner_commission_default_percent", None)
    provider = _provider(None)
    application = _application(provider=provider)
    with pytest.raises(PayoutError, match="процент"):
        await _confirm(_DB(provider=provider), application, _payment())
    assert application.registration_confirmed_at is None


@pytest.mark.asyncio
async def test_percent_set_after_payment_is_applied_at_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(owner_payouts.settings, "owner_commission_default_percent", None)
    provider = _provider(None)
    awaiting = OwnerPayout(
        id=uuid4(), application_id=uuid4(), payment_id=uuid4(), provider_id=provider.id,
        status=AWAITING_REGISTRATION, gross_kopeks=3_000_000,
    )
    provider.commission_percent = Decimal("10")
    payout = await _confirm(_DB(provider=provider, active=awaiting), _application(provider=provider), _payment())
    assert payout is awaiting and payout.payout_kopeks == 2_700_000


# ------------------------------------------------------------------
# Отметка выплаты и отмена
# ------------------------------------------------------------------


def _due_payout(provider):
    return OwnerPayout(
        id=uuid4(), application_id=uuid4(), payment_id=uuid4(), provider_id=provider.id,
        status=DUE, gross_kopeks=3_000_000, commission_percent=Decimal("20"),
        commission_kopeks=600_000, payout_kopeks=2_400_000, due_at=NOW,
    )


async def _mark(db, payout, application, payment, paid_on=date(2026, 10, 12), reference="15"):
    return await owner_payouts.mark_paid(
        db, payout=payout, application=application, payment=payment, paid_on=paid_on,
        bank_reference=reference, comment=None, admin_id=uuid4(), now=NOW,
    )


@pytest.mark.asyncio
async def test_mark_paid_records_transfer_and_payee_snapshot() -> None:
    provider = _provider()
    db = _DB(provider=provider)
    payout = await _mark(db, _due_payout(provider), _application(provider=provider), _payment(), reference=" 15 ")
    assert payout.status == PAID and payout.bank_reference == "15" and payout.paid_at == NOW
    assert payout.payee["settlement_account"] == "40702810000000000001"
    assert "№ 15 от 12.10.2026" in db.events(NotificationAudience.OWNER)[0].message


@pytest.mark.asyncio
async def test_mark_paid_refused_when_client_is_being_refunded() -> None:
    provider = _provider()
    payout = _due_payout(provider)
    with pytest.raises(PayoutError, match="Отмените"):
        await _mark(_DB(provider=provider), payout, _application(ApplicationStatus.REFUND_PENDING, provider=provider), _payment())
    assert payout.status == DUE


@pytest.mark.asyncio
async def test_mark_paid_only_from_due() -> None:
    provider = _provider()
    payout = _due_payout(provider)
    payout.status = AWAITING_REGISTRATION
    with pytest.raises(PayoutError, match="к перечислению"):
        await _mark(_DB(provider=provider), payout, _application(provider=provider), _payment())


@pytest.mark.asyncio
async def test_mark_paid_rejects_future_date() -> None:
    provider = _provider()
    with pytest.raises(PayoutError, match="будущем"):
        await _mark(_DB(provider=provider), _due_payout(provider), _application(provider=provider), _payment(), paid_on=date(2026, 10, 13))


@pytest.mark.asyncio
async def test_cancel_due_payout_tells_owner_but_paid_cannot_be_cancelled() -> None:
    provider = _provider()
    db = _DB(provider=provider)
    payout = await owner_payouts.cancel(db, payout=_due_payout(provider), reason="Возврат клиенту", admin_id=None, now=NOW)
    assert payout.status == CANCELLED and payout.cancel_reason == "Возврат клиенту"
    assert db.events(NotificationAudience.OWNER)

    paid = _due_payout(provider)
    paid.status = PAID
    with pytest.raises(PayoutError):
        await owner_payouts.cancel(_DB(provider=provider), payout=paid, reason="ошибка", admin_id=None, now=NOW)


@pytest.mark.asyncio
async def test_cancel_awaiting_payout_is_silent_for_owner() -> None:
    provider = _provider()
    db = _DB(provider=provider)
    payout = _due_payout(provider)
    payout.status = AWAITING_REGISTRATION
    await owner_payouts.cancel(db, payout=payout, reason="Заявка отменена", admin_id=None, now=NOW)
    assert db.events(NotificationAudience.OWNER) == []


@pytest.mark.asyncio
async def test_mark_paid_needs_owner_bank_details() -> None:
    provider = _provider()
    provider.settlement_account = None
    payout = _due_payout(provider)
    with pytest.raises(PayoutError, match="реквизиты"):
        await _mark(_DB(provider=provider), payout, _application(provider=provider), _payment())
    assert payout.status == DUE

