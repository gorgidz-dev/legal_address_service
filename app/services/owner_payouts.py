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
from datetime import date, datetime, timedelta, timezone
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

#: Даты платёжек и «сегодня» — по Москве: сервер живёт в UTC, и с 00:00 до 03:00
#: МСК сегодняшняя дата платёжки отклонялась бы как «будущая». Перехода на
#: летнее время в России нет с 2014 года — фиксированного смещения достаточно.
MOSCOW = timezone(timedelta(hours=3))


class PayoutError(Exception):
    """Шаг запрещён: текст — для админа, роутер отдаёт его как 409."""


_PERCENT_STEP = Decimal("0.01")


def resolve_commission_percent(provider: Provider) -> Optional[Decimal]:
    """Свой процент собственника или общий. Всегда ровно два знака: колонка
    Numeric(5,2) округлила бы 12.345 до 12.35, а комиссия была бы посчитана по
    12.345 — снимок процента разошёлся бы с удержанной суммой."""
    value = provider.commission_percent
    if value is None:
        value = settings.owner_commission_default_percent
    if value is None:
        return None
    return Decimal(value).quantize(_PERCENT_STEP, rounding=ROUND_HALF_UP)


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
    # По этому платежу выплата уже есть — в любом статусе. Отменённую не
    # переоткрываем молча: вторая строка на тот же платёж нарушила бы уникальный
    # индекс (500), а решение «всё-таки платить» — за человеком.
    by_payment = (
        await db.execute(select(OwnerPayout).where(OwnerPayout.payment_id == payment.id))
    ).scalar_one_or_none()
    if by_payment is not None:
        return by_payment
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
#: их по-разному («ул»/«улица», «вн.тер.г.»). Слова-метки номеров (дом, корпус,
#: строение, помещение) разбираются отдельно — см. _NUMBER_KINDS.
_ADDRESS_NOISE = frozenset({
    "г", "город", "гор", "ул", "улица", "пр", "пр-т", "пр-кт", "просп", "проспект", "пер",
    "переулок", "ш", "шоссе", "наб", "набережная", "пл", "площадь", "б-р", "бульвар", "проезд",
    "пр-д", "туп", "тупик", "мкр", "микрорайон", "р-н", "район", "обл", "область", "респ",
    "республика", "муниципальный", "округ", "мо", "вн", "тер", "внутригородская", "территория",
    "поселение", "пос", "поселок", "п", "с", "село", "деревня", "рф", "российская",
    "федерация", "россия", "эт", "этаж",
})
#: Метка → вид номера. «д» бывает и «деревней» («д. Марьино») — номером считаем,
#: только если за меткой идёт что-то с цифрой.
_NUMBER_KINDS = {
    **dict.fromkeys(("д", "дом", "вл", "владение", "двлд"), "house"),
    **dict.fromkeys(("к", "корп", "корпус"), "korpus"),
    **dict.fromkeys(("стр", "строение", "соор", "сооружение"), "building"),
    **dict.fromkeys(
        ("пом", "помещ", "помещение", "оф", "офис", "кв", "квартира", "ком", "комн", "комната"),
        "premises",
    ),
}
#: Дом, корпус и строение определяют здание: лишний корпус или строение в ЕГРЮЛ —
#: это уже другое здание (в Москве «стр. 1» — отдельный дом).
_BUILDING_KINDS = ("house", "korpus", "building")
_TOKEN = re.compile(r"[0-9a-zа-я]+(?:[/-][0-9a-zа-я]+)*")


@dataclass
class _ParsedAddress:
    words: set[str]
    numbers: dict[str, set[str]]  # вид → номера
    loose: set[str]  # номера без метки


def _parse_address(value: str, room_number: Optional[str] = None) -> _ParsedAddress:
    tokens = _TOKEN.findall(value.lower().replace("ё", "е"))
    parsed = _ParsedAddress(words=set(), numbers={}, loose=set())
    i = 0
    while i < len(tokens):
        token = tokens[i]
        kind = _NUMBER_KINDS.get(token)
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        if kind and any(ch.isdigit() for ch in following):
            parsed.numbers.setdefault(kind, set()).add(following)
            i += 2
            continue
        if any(ch.isdigit() for ch in token):
            if not (len(token) == 6 and token.isdigit()):  # почтовый индекс не сравниваем
                parsed.loose.add(token)
        elif token not in _ADDRESS_NOISE and token not in _NUMBER_KINDS and len(token) >= 3:
            parsed.words.add(token)
        i += 1
    if room_number and "premises" not in parsed.numbers:
        room = {t for t in _TOKEN.findall(room_number.lower()) if any(ch.isdigit() for ch in t)}
        if room:
            parsed.numbers["premises"] = room
    return parsed


def addresses_match(ours: str, egrul: Optional[str], room_number: Optional[str] = None) -> Optional[bool]:
    """Похоже ли, что юрадрес из ЕГРЮЛ — наш адрес. None — сравнивать не с чем.

    Подсказка админу, а не решение — подтверждает регистрацию всё равно человек,
    но «совпадает» снимает с него обязанность сверять вручную, поэтому правило
    строгое: все значимые слова нашего адреса (город, улица) есть в ЕГРЮЛ; дом,
    корпус и строение совпадают по видам (лишний корпус или строение — другое
    здание); помещение, если указано с обеих сторон, тоже совпадает.
    """
    if not egrul:
        return None
    our = _parse_address(ours, room_number)
    their = _parse_address(egrul)
    if not our.numbers and not our.loose:
        return None  # в нашем адресе нет ни одного номера — сравнивать нечего
    if not our.words <= their.words:
        return False
    for kind in _BUILDING_KINDS:
        if our.numbers.get(kind, set()) != their.numbers.get(kind, set()):
            return False
    if "premises" in our.numbers and "premises" in their.numbers:
        if our.numbers["premises"] != their.numbers["premises"]:
            return False
    their_all = their.loose.union(*their.numbers.values()) if their.numbers else their.loose
    return our.loose <= their_all


#: Организационно-правовые формы и служебные слова — в сравнении названий не
#: участвуют: в заявке «ООО «Ромашка»», в ЕГРЮЛ «ОБЩЕСТВО С ОГРАНИЧЕННОЙ
#: ОТВЕТСТВЕННОСТЬЮ "РОМАШКА"».
_OPF_WORDS = frozenset({
    "ооо", "ао", "пао", "зао", "оао", "нао", "ано", "ип", "общество", "с", "ограниченной",
    "ответственностью", "акционерное", "публичное", "непубличное", "закрытое", "открытое",
    "автономная", "некоммерческая", "организация",
})
_NAME_TOKEN = re.compile(r"[0-9a-zа-я]+")


def company_name_core(value: Optional[str]) -> str:
    """Название без формы и кавычек: «ООО "Ромашка-Плюс"» → «ромашка плюс»."""
    tokens = _NAME_TOKEN.findall((value or "").lower().replace("ё", "е"))
    return " ".join(token for token in tokens if token not in _OPF_WORDS)


def names_match(expected: Optional[str], egrul: Optional[str]) -> Optional[bool]:
    """Совпадает ли название из заявки с ЕГРЮЛ. None — сравнивать не с чем."""
    ours, theirs = company_name_core(expected), company_name_core(egrul)
    if not ours or not theirs:
        return None
    return ours == theirs


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
    # Первичная регистрация сверяется по названию и адресу (ИНН новой компании
    # заранее неизвестен); смена адреса — по ИНН и адресу (решение владельца).
    expected_name: Optional[str] = None
    name_matches: Optional[bool] = None
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
            "expected_name": self.expected_name,
            "name_matches": self.name_matches,
            "warnings": list(self.warnings),
            "checked_at": checked_at.isoformat(),
        }


def expected_company_name(application: Application) -> Optional[str]:
    """Название, под которым компанию подали в ИФНС (первичная регистрация):
    из расписки, если она разобрана, иначе — из заявки."""
    receipt = application.ifns_receipt_data or {}
    return receipt.get("company_name") or application.planned_client_name or application.company_name


def _check_from_party(
    application: Application, our_address: str, found: Any, room_number: Optional[str]
) -> RegistrationCheck:
    match = addresses_match(our_address, found.legal_address, room_number)
    initial = application.type == "initial_registration"
    expected = expected_company_name(application) if initial else None
    name_match = names_match(expected, found.full_name) if initial else None
    warnings: list[str] = []
    if match is False:
        warnings.append("Юрадрес в ЕГРЮЛ не похож на адрес заявки — сравните вручную.")
    elif match is None:
        warnings.append("В ЕГРЮЛ нет юрадреса — сравнить не с чем.")
    if initial and name_match is not True:
        warnings.append(f"Название в ЕГРЮЛ не совпадает с заявкой («{expected or '—'}») — сравните вручную.")
    status = getattr(found.egrul_status, "value", found.egrul_status)
    if status != "ACTIVE":
        warnings.append(f"Статус компании в ЕГРЮЛ — {status}.")
    registered = getattr(found, "registration_date", None)
    if (
        registered is not None
        and initial
        and application.created_at is not None
        and registered < application.created_at.date()
    ):
        warnings.append(
            "Компания зарегистрирована раньше, чем создана заявка, — для первичной "
            "регистрации это подозрительно: та ли это компания?"
        )
    return RegistrationCheck(
        inn=found.inn,
        found=True,
        full_name=found.full_name,
        ogrn=found.ogrn,
        registration_date=registered,
        egrul_status=status,
        legal_address=found.legal_address,
        our_address=our_address,
        address_matches=match,
        expected_name=expected,
        name_matches=name_match,
        warnings=tuple(warnings),
    )


async def check_registration(
    application: Application, our_address: str, inn: str, dadata: Any, room_number: Optional[str] = None
) -> RegistrationCheck:
    """Запрос в ЕГРЮЛ (DaData) по ИНН: адрес, а для первичной регистрации и название.

    Кэш DaData сбрасывается: адрес компании меняется как раз в тот момент,
    который мы проверяем, — вчерашний ответ из кэша здесь вреден.
    """
    dadata.invalidate(inn)
    found = await dadata.lookup(inn)
    if found is None:
        return RegistrationCheck(
            inn=inn, found=False, our_address=our_address,
            expected_name=expected_company_name(application) if application.type == "initial_registration" else None,
            warnings=("Компания с таким ИНН в ЕГРЮЛ не найдена — возможно, запись ещё не появилась.",),
        )
    return _check_from_party(application, our_address, found, room_number)


async def search_registration_by_name(
    application: Application, our_address: str, name: str, dadata: Any, room_number: Optional[str] = None
) -> list[RegistrationCheck]:
    """Первичная регистрация: ищем компанию в ЕГРЮЛ по названию и сверяем адрес.

    Кандидаты с совпавшими названием и адресом — первыми; админ выбирает
    нужного, подтверждение дальше идёт по его ИНН (`check_registration`).
    """
    found = await dadata.search_by_name(name)
    checks = [_check_from_party(application, our_address, party, room_number) for party in found]
    return sorted(
        checks,
        key=lambda c: (c.name_matches is not True, c.address_matches is not True, c.full_name or ""),
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


@dataclass
class RegistrationOutcome:
    """Итог подтверждения регистрации.

    payout — выплата собственнику, если деньги принимала площадка (None — выплаты
    по заявке нет). payout_held — почему выплата не перешла «к перечислению»,
    хотя регистрацию подтвердили (отменена, возврат клиенту): это админу.
    """
    payout: Optional[OwnerPayout]
    payout_held: Optional[str] = None


async def confirm_registration(
    db: AsyncSession,
    *,
    application: Application,
    payment: Optional[Payment],
    check: RegistrationCheck,
    accept_address_mismatch: bool,
    admin_id: Any,
    now: datetime,
    required_inn: Optional[str] = None,
) -> RegistrationOutcome:
    """Регистрация компании клиента подтверждена по ЕГРЮЛ.

    Это факт о заявке (последний шаг статус-трекера), а не только условие
    выплаты: подтверждать можно любую заявку с выданными документами. Если деньги
    принимала площадка (`payment` — её платёж), выплата собственнику переходит
    «к перечислению». Если выплату двигать нельзя (её отменили, клиенту
    возвращали деньги), регистрация всё равно подтверждается — иначе трекер
    клиента и собственника застрял бы навсегда, — а выплата остаётся как была,
    и причина уходит админу в payout_held.

    Повторно подтверждать можно только ради выплаты, которая ждала: например,
    возврат не прошёл и деньги остались у площадки.

    Заявка и платёж должны быть заблокированы вызывающим (FOR UPDATE).
    """
    if application.status not in REGISTRATION_ALLOWED:
        raise PayoutError("Документы клиенту ещё не выданы — регистрацию подтверждать рано.")
    already = application.registration_confirmed_at is not None
    platform_paid = payment is not None and payment.provider in PLATFORM_COLLECTED
    if not check.found:
        raise PayoutError("Компания с этим ИНН в ЕГРЮЛ не найдена.")
    if required_inn is not None and check.inn != required_inn:
        # Смена адреса: компания известна заранее — подтверждаем только её.
        raise PayoutError(f"По заявке меняет адрес компания с ИНН {required_inn}, а не {check.inn}.")
    initial = application.type == "initial_registration"
    mismatched = check.address_matches is not True or (initial and check.name_matches is not True)
    if mismatched and not accept_address_mismatch:
        raise PayoutError(
            ("Название или юрадрес" if initial else "Юрадрес")
            + " в ЕГРЮЛ не совпал с заявкой. Если вы сверили вручную и это та же компания и тот же "
            "адрес — подтвердите с отметкой «сверено вручную»."
        )

    # Тестовый терминал или заявка без собственника выплаты не порождают —
    # регистрацию это не отменяет.
    payout = await ensure_payout(db, application, payment) if platform_paid else None
    movable = payout is not None and payout.status == AWAITING_REGISTRATION
    held: Optional[str] = None
    if payout is not None and payout.status == CANCELLED:
        held = (
            "Выплату по этому платежу отменили — она не переоткрывается. Если деньги собственнику "
            "всё же положены, рассчитайтесь с ним вне реестра."
        )
    elif movable:
        blockers = payout_blockers(application, payment)
        if blockers:
            held = (
                "Выплата осталась в ожидании: " + "; ".join(blockers) + ". Когда станет ясно, "
                "положена ли она, отмените её или подтвердите регистрацию из реестра ещё раз."
            )
    if already and (not movable or held):
        raise PayoutError("Регистрация по этой заявке уже подтверждена." + (f" {held}" if held else ""))
    release = movable and held is None
    if release and payout.commission_percent is None:
        # Это поправимо (админ задаст процент) — до любых записей.
        provider = await db.get(Provider, payout.provider_id)
        percent = resolve_commission_percent(provider) if provider else None
        if percent is None:
            raise PayoutError(
                "Не задан процент комиссии: укажите его у собственника или общий "
                "OWNER_COMMISSION_DEFAULT_PERCENT."
            )
        _apply_percent(payout, percent)

    if not already:
        snapshot = check.snapshot(now)
        snapshot["accepted_address_mismatch"] = bool(accept_address_mismatch and mismatched)
        application.registration_inn = check.inn
        application.registration_check = snapshot
        application.registration_confirmed_at = now
        application.registration_confirmed_by = admin_id
    if release:
        payout.status = DUE
        payout.due_at = now
    await db.flush()

    events: list[tuple[NotificationAudience, str, str, dict[str, Any]]] = []
    if release:
        events.append((
            NotificationAudience.OWNER,
            "Регистрация подтверждена — выплата в очереди",
            f"Компания клиента зарегистрирована по вашему адресу. К выплате {_rub(payout.payout_kopeks)}: "
            f"оплата {_rub(payout.gross_kopeks)} минус комиссия площадки {payout.commission_percent}%.",
            {"registration_confirmed": True, "payout_id": str(payout.id), "payout_status": payout.status},
        ))
    elif not already:
        # Почему выплата встала (отмена, возврат) — внутреннее дело площадки.
        events.append((
            NotificationAudience.OWNER,
            "Регистрация подтверждена",
            "Компания клиента зарегистрирована по вашему адресу — площадка сверила с ЕГРЮЛ.",
            {"registration_confirmed": True},
        ))
    if not already:
        events.append((
            NotificationAudience.CLIENT,
            "Регистрация подтверждена",
            "Площадка сверила с ЕГРЮЛ: компания зарегистрирована по адресу из заявки.",
            {"registration_confirmed": True},
        ))
    for audience, title, message, payload in events:
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=audience,
            title=title,
            message=message,
            payload=payload,
            created_by=admin_id,
        )
    return RegistrationOutcome(payout=payout, payout_held=held)


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
    if paid_on > now.astimezone(MOSCOW).date():
        raise PayoutError("Дата платёжки не может быть в будущем.")
    reference = bank_reference.strip()
    if not reference:
        raise PayoutError("Укажите номер платёжного поручения.")
    provider = await db.get(Provider, payout.provider_id)
    if provider is None or not (provider.settlement_account and provider.bik):
        raise PayoutError(
            "У собственника не заполнены банковские реквизиты (расчётный счёт и БИК) — "
            "внесите их в карточке собственника."
        )
    payout.status = PAID
    payout.paid_on = paid_on
    payout.paid_at = now
    payout.paid_by = admin_id
    payout.bank_reference = reference
    payout.comment = (comment or "").strip() or None
    payout.payee = _payee_snapshot(provider)
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
