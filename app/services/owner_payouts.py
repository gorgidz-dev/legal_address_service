"""Выплаты собственникам: сколько, когда и с какими проверками.

Модель денег (CLAUDE.md, «Как устроены деньги»): если платёж клиента принимает
площадка (эквайринг Т-Банка), площадка перечисляет собственнику цену адреса за
вычетом своей комиссии — и только после успешной регистрации компании клиента
по этому адресу (решение владельца 12.10.2026). Оплата по счёту собственника
(manual_invoice) идёт мимо площадки — выплаты по ней нет.

Жизненный цикл выплаты:

    оплата прошла ──► awaiting_registration ──► due ──► paid
                              │                  │
                              └──── cancelled ◄──┘

- awaiting_registration — заводится в той же транзакции, где платёж стал
  «оплачен» (`ensure_payout` из tbank_payments._on_paid). Процент комиссии и
  суммы — снимок на этот момент.
- due — админ сверил ИНН компании с ЕГРЮЛ и подтвердил регистрацию.
- paid — админ перевёл деньги в банке и отметил выплату (дата и номер
  платёжки, снимок реквизитов получателя).
- cancelled — отменена админом с причиной (возврат клиенту, отмена заявки).

Переводы денег система не делает: выплаты ручные, по реестру. Перед каждым
шагом проверяется живое состояние платежа и заявки (`payout_blockers`): возврат,
спор или отмена заявки шаг запрещают.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    NotificationAudience,
    PaymentProvider,
    PaymentStatus,
)
from app.models.application import Application
from app.models.owner_payout import OwnerPayout
from app.models.payment import Payment
from app.models.provider import Provider
from app.services.notification_events import create_application_event

AWAITING_REGISTRATION = "awaiting_registration"
DUE = "due"
PAID = "paid"
CANCELLED = "cancelled"

#: Деньги клиента принимает площадка — значит, ей и рассчитываться с собственником.
PLATFORM_COLLECTED = frozenset({PaymentProvider.TBANK.value, PaymentProvider.CDEK_PAY.value})

#: Регистрацию подтверждаем, когда документы выданы клиенту. Спор — нет: пока он
#: не закрыт, неизвестно, останутся ли деньги у площадки.
REGISTRATION_ALLOWED = frozenset({
    ApplicationStatus.READY_FOR_CLIENT.value,
    ApplicationStatus.COMPLETED.value,
})

#: Заявка в таком статусе — деньги могут уйти клиенту обратно.
_BLOCKING_APPLICATION = {
    ApplicationStatus.DISPUTE.value: "по заявке открыт спор",
    ApplicationStatus.REFUND_PENDING.value: "по заявке готовится возврат клиенту",
    ApplicationStatus.REFUNDED.value: "клиенту сделан возврат",
    ApplicationStatus.CANCELLED.value: "заявка отменена",
}

_PARTIAL_REFUNDED = "PARTIAL_REFUNDED"  # статус банка, см. tbank_payments


class PayoutError(Exception):
    """Шаг запрещён: текст — для админа, роутер отдаёт его как 409."""


def resolve_commission_percent(provider: Provider) -> Optional[Decimal]:
    if provider.commission_percent is not None:
        return Decimal(provider.commission_percent)
    return settings.owner_commission_default_percent


def split(gross_kopeks: int, percent: Decimal) -> tuple[int, int]:
    """(комиссия, к выплате) в копейках. Комиссия округляется до копейки
    по-бухгалтерски, выплата — остаток: вместе всегда ровно gross."""
    commission = int(
        (Decimal(gross_kopeks) * Decimal(percent) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    return commission, gross_kopeks - commission


def _apply_percent(payout: OwnerPayout, percent: Decimal) -> None:
    commission, payout_kopeks = split(payout.gross_kopeks, percent)
    if payout_kopeks <= 0:
        raise PayoutError("При таком проценте собственнику не остаётся ничего — проверьте процент.")
    payout.commission_percent = percent
    payout.commission_kopeks = commission
    payout.payout_kopeks = payout_kopeks


def payout_blockers(application: Application, payment: Payment) -> list[str]:
    """Почему двигать выплату сейчас нельзя (пустой список — можно)."""
    reasons: list[str] = []
    if payment.status != PaymentStatus.SUCCEEDED.value:
        reasons.append(f"платёж клиента не в статусе «оплачен» (сейчас «{payment.status}»)")
    if payment.refunded_kopeks or payment.provider_status == _PARTIAL_REFUNDED:
        reasons.append("клиенту возвращалась часть денег — сумму выплаты согласуйте вручную")
    reason = _BLOCKING_APPLICATION.get(application.status)
    if reason:
        reasons.append(reason)
    return reasons


async def active_payout(db: AsyncSession, application_id: Any) -> Optional[OwnerPayout]:
    return (
        await db.execute(
            select(OwnerPayout).where(
                OwnerPayout.application_id == application_id,
                OwnerPayout.status != CANCELLED,
            )
        )
    ).scalar_one_or_none()


async def ensure_payout(
    db: AsyncSession, application: Application, payment: Payment
) -> Optional[OwnerPayout]:
    """Завести выплату по оплаченной заявке (идемпотентно). None — выплаты не будет.

    Вызывается под блокировкой строки заявки — двух живых выплат на заявку не
    бывает и без того (частичный уникальный индекс), но гонку лучше не начинать.
    """
    # Импорт здесь: tbank_payments сам зовёт этот модуль.
    from app.services.tbank_payments import is_demo_terminal

    if payment.provider not in PLATFORM_COLLECTED:
        return None
    if is_demo_terminal(payment.provider_account):
        return None  # тестовый терминал: денег нет, платить собственнику нечем
    existing = await active_payout(db, application.id)
    if existing is not None:
        return existing
    provider = await db.get(Provider, application.provider_id)
    if provider is None:
        return None
    payout = OwnerPayout(
        application_id=application.id,
        payment_id=payment.id,
        provider_id=provider.id,
        status=AWAITING_REGISTRATION,
        gross_kopeks=payment.amount_kopeks,
    )
    percent = resolve_commission_percent(provider)
    if percent is not None:
        _apply_percent(payout, percent)
    db.add(payout)
    await db.flush()
    return payout


# ============================================================
# Сверка регистрации с ЕГРЮЛ
# ============================================================

#: Служебные слова адреса — по ним не сравниваем: DaData и наш каталог пишут
#: их по-разному («ул»/«улица», «д.»/«дом», «вн.тер.г.»).
_ADDRESS_NOISE = frozenset({
    "г", "город", "гор", "ул", "улица", "д", "дом", "к", "корп", "корпус", "стр", "строение",
    "пом", "помещ", "помещение", "кв", "квартира", "оф", "офис", "эт", "этаж", "ком", "комн",
    "комната", "пр", "пр-т", "просп", "проспект", "пер", "переулок", "ш", "шоссе", "наб",
    "набережная", "пл", "площадь", "б-р", "бульвар", "проезд", "туп", "тупик", "мкр",
    "микрорайон", "вл", "владение", "р-н", "район", "обл", "область", "респ", "республика",
    "муниципальный", "округ", "мо", "вн", "тер", "внутригородская", "территория", "поселение",
    "пос", "поселок", "п", "с", "село", "деревня", "рф", "российская", "федерация", "россия",
})
_TOKEN = re.compile(r"[0-9a-zа-я]+")


def _address_tokens(value: str) -> tuple[set[str], set[str]]:
    """(слова, номера) адреса без индекса и служебных слов."""
    words: set[str] = set()
    numbers: set[str] = set()
    for token in _TOKEN.findall(value.lower().replace("ё", "е")):
        if token in _ADDRESS_NOISE:
            continue
        if any(ch.isdigit() for ch in token):
            if len(token) == 6 and token.isdigit():
                continue  # почтовый индекс: в каталоге его обычно нет
            numbers.add(token)
        elif len(token) >= 3:
            words.add(token)
    return words, numbers


def addresses_match(ours: str, egrul: Optional[str]) -> Optional[bool]:
    """Похоже ли, что юрадрес из ЕГРЮЛ — наш адрес. None — сравнивать не с чем.

    Подсказка админу, а не решение: все номера нашего адреса (дом, корпус,
    помещение) должны найтись в адресе ЕГРЮЛ, и большая часть слов (город,
    улица) — тоже. Подтверждает регистрацию всё равно человек.
    """
    if not egrul:
        return None
    our_words, our_numbers = _address_tokens(ours)
    their_words, their_numbers = _address_tokens(egrul)
    if not our_numbers or not our_numbers <= their_numbers:
        return False
    if not our_words:
        return True
    return len(our_words & their_words) * 3 >= len(our_words) * 2


@dataclass
class RegistrationCheck:
    inn: str
    found: bool
    full_name: Optional[str] = None
    ogrn: Optional[str] = None
    registration_date: Optional[date] = None
    egrul_status: Optional[str] = None
    legal_address: Optional[str] = None
    our_address: Optional[str] = None
    address_matches: Optional[bool] = None
    warnings: tuple[str, ...] = ()

    def snapshot(self, checked_at: datetime) -> dict[str, Any]:
        return {
            "inn": self.inn,
            "found": self.found,
            "full_name": self.full_name,
            "ogrn": self.ogrn,
            "registration_date": self.registration_date.isoformat() if self.registration_date else None,
            "egrul_status": self.egrul_status,
            "legal_address": self.legal_address,
            "our_address": self.our_address,
            "address_matches": self.address_matches,
            "warnings": list(self.warnings),
            "checked_at": checked_at.isoformat(),
        }


async def check_registration(
    application: Application, our_address: str, inn: str, dadata: Any
) -> RegistrationCheck:
    """Запрос в ЕГРЮЛ (DaData) по ИНН и сравнение юрадреса с адресом заявки.

    Кэш DaData сбрасывается: адрес компании меняется как раз в тот момент,
    который мы проверяем, — вчерашний ответ из кэша здесь вреден.
    """
    dadata.invalidate(inn)
    found = await dadata.lookup(inn)
    if found is None:
        return RegistrationCheck(
            inn=inn, found=False, our_address=our_address,
            warnings=("Компания с таким ИНН в ЕГРЮЛ не найдена — возможно, запись ещё не появилась.",),
        )
    match = addresses_match(our_address, found.legal_address)
    warnings: list[str] = []
    if match is False:
        warnings.append("Юрадрес в ЕГРЮЛ не похож на адрес заявки — сравните вручную.")
    elif match is None:
        warnings.append("В ЕГРЮЛ нет юрадреса — сравнить не с чем.")
    status = getattr(found.egrul_status, "value", found.egrul_status)
    if status != "ACTIVE":
        warnings.append(f"Статус компании в ЕГРЮЛ — {status}.")
    registered = getattr(found, "registration_date", None)
    if (
        registered is not None
        and application.type == "initial_registration"
        and application.created_at is not None
        and registered < application.created_at.date()
    ):
        warnings.append(
            "Компания зарегистрирована раньше, чем создана заявка, — для первичной "
            "регистрации это подозрительно: тот ли ИНН?"
        )
    return RegistrationCheck(
        inn=inn,
        found=True,
        full_name=found.full_name,
        ogrn=found.ogrn,
        registration_date=registered,
        egrul_status=status,
        legal_address=found.legal_address,
        our_address=our_address,
        address_matches=match,
        warnings=tuple(warnings),
    )


def _rub(kopeks: Optional[int]) -> str:
    if kopeks is None:
        return "—"
    return f"{kopeks / 100:,.2f}".replace(",", " ").replace(".", ",") + " ₽"


async def _event(
    db: AsyncSession, application_id: Any, audience: NotificationAudience, title: str, message: str,
    payout: OwnerPayout, created_by: Any = None,
) -> None:
    await create_application_event(
        db=db,
        application_id=application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=audience,
        title=title,
        message=message,
        payload={"payout_id": str(payout.id), "payout_status": payout.status},
        created_by=created_by,
    )


async def confirm_registration(
    db: AsyncSession,
    *,
    application: Application,
    payment: Payment,
    check: RegistrationCheck,
    accept_address_mismatch: bool,
    admin_id: Any,
    now: datetime,
) -> OwnerPayout:
    """Регистрация подтверждена → выплата «к перечислению».

    Заявка и платёж должны быть заблокированы вызывающим (FOR UPDATE).
    """
    if application.registration_confirmed_at is not None:
        raise PayoutError("Регистрация по этой заявке уже подтверждена.")
    if payment.provider not in PLATFORM_COLLECTED:
        raise PayoutError("Деньги по этой заявке получал собственник напрямую — выплаты нет.")
    if application.status not in REGISTRATION_ALLOWED:
        raise PayoutError("Документы клиенту ещё не выданы — регистрацию подтверждать рано.")
    blockers = payout_blockers(application, payment)
    if blockers:
        raise PayoutError("Нельзя: " + "; ".join(blockers) + ".")
    if not check.found:
        raise PayoutError("Компания с этим ИНН в ЕГРЮЛ не найдена.")
    if check.address_matches is not True and not accept_address_mismatch:
        raise PayoutError(
            "Юрадрес в ЕГРЮЛ не совпал с адресом заявки. Если вы сверили вручную и это тот же "
            "адрес — подтвердите с отметкой «адрес сверен вручную»."
        )

    payout = await ensure_payout(db, application, payment)
    if payout is None:
        raise PayoutError("По этому платежу выплата не положена (тестовый терминал или нет собственника).")
    if payout.status != AWAITING_REGISTRATION:
        raise PayoutError(f"Выплата уже в статусе «{payout.status}».")
    if payout.commission_percent is None:
        provider = await db.get(Provider, payout.provider_id)
        percent = resolve_commission_percent(provider) if provider else None
        if percent is None:
            raise PayoutError(
                "Не задан процент комиссии: укажите его у собственника или общий "
                "OWNER_COMMISSION_DEFAULT_PERCENT."
            )
        _apply_percent(payout, percent)

    snapshot = check.snapshot(now)
    snapshot["accepted_address_mismatch"] = bool(accept_address_mismatch and check.address_matches is not True)
    application.registration_inn = check.inn
    application.registration_check = snapshot
    application.registration_confirmed_at = now
    application.registration_confirmed_by = admin_id
    payout.status = DUE
    payout.due_at = now
    await db.flush()

    await _event(
        db, application.id, NotificationAudience.OWNER,
        "Регистрация подтверждена — выплата в очереди",
        f"Компания клиента зарегистрирована по вашему адресу. К выплате {_rub(payout.payout_kopeks)}: "
        f"оплата {_rub(payout.gross_kopeks)} минус комиссия площадки {payout.commission_percent}%.",
        payout, admin_id,
    )
    await _event(
        db, application.id, NotificationAudience.CLIENT,
        "Регистрация подтверждена",
        "Площадка сверила с ЕГРЮЛ: компания зарегистрирована по адресу из заявки.",
        payout, admin_id,
    )
    return payout


def _payee_snapshot(provider: Provider) -> dict[str, Any]:
    return {
        "full_name": provider.full_name,
        "inn": provider.inn,
        "kpp": provider.kpp,
        "bank_name": provider.bank_name,
        "settlement_account": provider.settlement_account,
        "corr_account": provider.corr_account,
        "bik": provider.bik,
    }


async def mark_paid(
    db: AsyncSession,
    *,
    payout: OwnerPayout,
    application: Application,
    payment: Payment,
    paid_on: date,
    bank_reference: str,
    comment: Optional[str],
    admin_id: Any,
    now: datetime,
) -> OwnerPayout:
    """Админ перевёл деньги собственнику. Выплата заблокирована вызывающим."""
    if payout.status != DUE:
        raise PayoutError(
            "Отметить выплату можно только «к перечислению» "
            f"(сейчас «{payout.status}»)."
        )
    blockers = payout_blockers(application, payment)
    if blockers:
        raise PayoutError("Нельзя: " + "; ".join(blockers) + ". Отмените выплату, если она больше не положена.")
    if paid_on > now.date():
        raise PayoutError("Дата платёжки не может быть в будущем.")
    reference = bank_reference.strip()
    if not reference:
        raise PayoutError("Укажите номер платёжного поручения.")
    provider = await db.get(Provider, payout.provider_id)
    payout.status = PAID
    payout.paid_on = paid_on
    payout.paid_at = now
    payout.paid_by = admin_id
    payout.bank_reference = reference
    payout.comment = (comment or "").strip() or None
    payout.payee = _payee_snapshot(provider) if provider else None
    await db.flush()
    await _event(
        db, application.id, NotificationAudience.OWNER,
        "Выплата отправлена",
        f"Площадка перечислила {_rub(payout.payout_kopeks)} "
        f"(платёжное поручение № {reference} от {paid_on.strftime('%d.%m.%Y')}).",
        payout, admin_id,
    )
    return payout


async def cancel(
    db: AsyncSession, *, payout: OwnerPayout, reason: str, admin_id: Any, now: datetime
) -> OwnerPayout:
    """Отменить выплату (возврат клиенту, отмена заявки). Выплаченную — нельзя."""
    if payout.status not in (AWAITING_REGISTRATION, DUE):
        raise PayoutError(f"Выплату в статусе «{payout.status}» отменить нельзя.")
    text = reason.strip()
    if not text:
        raise PayoutError("Укажите причину отмены.")
    was_due = payout.status == DUE
    payout.status = CANCELLED
    payout.cancelled_at = now
    payout.cancel_reason = text
    await db.flush()
    if was_due:
        # Собственнику уже сообщили «выплата в очереди» — сообщаем и об отмене.
        await _event(
            db, payout.application_id, NotificationAudience.OWNER,
            "Выплата отменена",
            f"Выплата {_rub(payout.payout_kopeks)} по заявке отменена: {text}",
            payout, admin_id,
        )
    return payout
