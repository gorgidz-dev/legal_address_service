"""Выплаты собственникам: реестр админа, подтверждение регистрации, отметка выплаты.

Правила и жизненный цикл — app/services/owner_payouts.py. Здесь — доступ,
блокировки строк и ответы. Порядок блокировок везде один, как в автомате
платежей Т-Банка: платёж → заявка → выплата, — иначе встречные транзакции
могли бы ждать друг друга.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_owner, utcnow
from app.database import get_db
from app.enums import ApplicationType, PaymentStatus
from app.models.address import Address
from app.models.application import Application
from app.models.client import Client
from app.models.owner_payout import OwnerPayout
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.user import User
from app.schemas.owner_payout import (
    AdminPayoutRead,
    OwnerPayoutRead,
    PayoutCancelRequest,
    PayoutMarkPaidRequest,
    PayoutPayee,
    PayoutStatus,
    RegistrationCheckRead,
    RegistrationConfirmRequest,
    RegistrationConfirmResult,
    RegistrationLookupRead,
    RegistrationLookupRequest,
)
from app.routers.owner_dashboard import OWNER_VISIBLE_STATUSES
from app.services import owner_payouts
from app.services.dadata import DaDataError, DaDataNotConfigured, get_dadata_service
from app.services.owner_payouts import PayoutError
from app.services.tbank_payments import lock_payment

router = APIRouter(prefix="/payouts", tags=["payouts"])

#: Платёж, по которому может идти выплата: оплачен, или деньги уже уходят назад
#: (тогда блокировки объяснят админу, почему двигать нельзя).
_PAID_LIKE = (
    PaymentStatus.SUCCEEDED.value,
    PaymentStatus.REFUND_REQUESTED.value,
    PaymentStatus.REFUNDED.value,
)


def _conflict(e: PayoutError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(e))


def _label(application: Application) -> str:
    return application.company_name or application.planned_client_name or "Заявка"


async def _lock_application(db: AsyncSession, application_id: UUID) -> Optional[Application]:
    stmt = (
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _lock_payout(db: AsyncSession, payout_id: UUID) -> Optional[OwnerPayout]:
    stmt = (
        select(OwnerPayout)
        .where(OwnerPayout.id == payout_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _platform_payment_id(db: AsyncSession, application_id: UUID) -> Optional[UUID]:
    """Платёж, принятый площадкой по заявке: тот, на который заведена выплата,
    иначе последний оплаченный через эквайринг."""
    payout = await owner_payouts.active_payout(db, application_id)
    if payout is not None:
        return payout.payment_id
    return (
        await db.execute(
            select(Payment.id)
            .where(
                Payment.application_id == application_id,
                Payment.provider.in_(owner_payouts.PLATFORM_COLLECTED),
                Payment.status.in_(_PAID_LIKE),
            )
            .order_by(Payment.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _admin_views(db: AsyncSession, payouts: list[OwnerPayout]) -> list[AdminPayoutRead]:
    if not payouts:
        return []
    app_ids = {p.application_id for p in payouts}
    applications = {
        a.id: a for a in (await db.execute(select(Application).where(Application.id.in_(app_ids)))).scalars()
    }
    providers = {
        p.id: p
        for p in (
            await db.execute(select(Provider).where(Provider.id.in_({p.provider_id for p in payouts})))
        ).scalars()
    }
    payments = {
        p.id: p
        for p in (
            await db.execute(select(Payment).where(Payment.id.in_({p.payment_id for p in payouts})))
        ).scalars()
    }
    address_ids = {a.address_id for a in applications.values()}
    addresses = {
        a.id: a for a in (await db.execute(select(Address).where(Address.id.in_(address_ids)))).scalars()
    }
    client_ids = {a.client_id for a in applications.values() if a.client_id}
    clients = (
        {c.id: c for c in (await db.execute(select(Client).where(Client.id.in_(client_ids)))).scalars()}
        if client_ids
        else {}
    )

    views: list[AdminPayoutRead] = []
    for payout in payouts:
        application = applications[payout.application_id]
        provider = providers[payout.provider_id]
        payment = payments[payout.payment_id]
        address = addresses.get(application.address_id)
        client = clients.get(application.client_id) if application.client_id else None
        if payout.status == owner_payouts.PAID and payout.payee:
            payee = PayoutPayee(**payout.payee)
        else:
            payee = PayoutPayee(**owner_payouts._payee_snapshot(provider))
        suggested = application.registration_inn or (
            client.inn if client and application.type == ApplicationType.ADDRESS_CHANGE.value else None
        )
        live = payout.status in (owner_payouts.AWAITING_REGISTRATION, owner_payouts.DUE)
        views.append(
            AdminPayoutRead(
                id=payout.id,
                status=payout.status,
                application_id=application.id,
                application_label=_label(application),
                application_type=application.type,
                application_status=application.status,
                address=address.full_address if address else None,
                provider_id=provider.id,
                provider_name=provider.short_name,
                payment_id=payment.id,
                payment_status=payment.status,
                gross_kopeks=payout.gross_kopeks,
                commission_percent=payout.commission_percent,
                commission_kopeks=payout.commission_kopeks,
                payout_kopeks=payout.payout_kopeks,
                due_at=payout.due_at,
                paid_on=payout.paid_on,
                paid_at=payout.paid_at,
                bank_reference=payout.bank_reference,
                comment=payout.comment,
                cancelled_at=payout.cancelled_at,
                cancel_reason=payout.cancel_reason,
                created_at=payout.created_at,
                payee=payee,
                registration_inn=application.registration_inn,
                registration_inn_submitted_at=application.registration_inn_submitted_at,
                registration_confirmed_at=application.registration_confirmed_at,
                registration_expected_on=application.registration_expected_on,
                registration_check=application.registration_check,
                suggested_inn=suggested,
                blockers=owner_payouts.payout_blockers(application, payment) if live else [],
            )
        )
    return views


async def _admin_view(db: AsyncSession, payout: OwnerPayout) -> AdminPayoutRead:
    return (await _admin_views(db, [payout]))[0]


# ============================================================
# Реестр
# ============================================================


@router.get("", response_model=list[AdminPayoutRead])
async def list_payouts(
    status_filter: Optional[PayoutStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[AdminPayoutRead]:
    stmt = select(OwnerPayout).order_by(OwnerPayout.created_at.desc())
    if status_filter:
        stmt = stmt.where(OwnerPayout.status == status_filter)
    payouts = list((await db.execute(stmt)).scalars())
    return await _admin_views(db, payouts)


@router.get("/mine", response_model=list[OwnerPayoutRead])
async def my_payouts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[OwnerPayoutRead]:
    """Выплаты собственника — только его и только то, что ему положено знать."""
    if user.provider_id is None:
        return []
    # Только по заявкам, которые собственник уже видит в кабинете: оплаченная
    # заявка до назначения админом ему не показывается — и выплата по ней тоже,
    # иначе раздел «Выплаты» раскрывал бы клиента раньше времени.
    payouts = list(
        (
            await db.execute(
                select(OwnerPayout)
                .join(Application, Application.id == OwnerPayout.application_id)
                .where(
                    OwnerPayout.provider_id == user.provider_id,
                    Application.status.in_(OWNER_VISIBLE_STATUSES),
                )
                .order_by(OwnerPayout.created_at.desc())
            )
        ).scalars()
    )
    return [
        OwnerPayoutRead(**view.model_dump(include=set(OwnerPayoutRead.model_fields)))
        for view in await _admin_views(db, payouts)
    ]


# ============================================================
# Регистрация компании клиента
# ============================================================


async def _load_target(db: AsyncSession, application_id: UUID) -> tuple[Application, Address, Optional[str]]:
    """Заявка, её адрес и ИНН компании, если он известен заранее (смена адреса)."""
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    address = await db.get(Address, application.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")
    known_inn = None
    if application.type == ApplicationType.ADDRESS_CHANGE.value and application.client_id:
        client = await db.get(Client, application.client_id)
        known_inn = client.inn if client is not None else None
    return application, address, known_inn


def _dadata():
    try:
        return get_dadata_service()
    except DaDataNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


async def _with_taken_warning(
    db: AsyncSession, application: Application, check: owner_payouts.RegistrationCheck
) -> owner_payouts.RegistrationCheck:
    """Подсказка «этот ИНН уже подтверждён по другой заявке» — решает админ (одна
    компания законно бывает в нескольких заявках, например при продлении)."""
    if not check.found:
        return check
    taken = (
        await db.execute(
            select(Application.company_name, Application.planned_client_name).where(
                Application.registration_inn == check.inn,
                Application.registration_confirmed_at.is_not(None),
                Application.id != application.id,
            )
        )
    ).first()
    if taken is not None:
        check.warnings = (
            *check.warnings,
            f"Этот ИНН уже подтверждён по другой заявке ({taken[0] or taken[1] or 'без названия'}) — "
            "проверьте, что это не ошибка.",
        )
    return check


async def _run_check(
    db: AsyncSession, application_id: UUID, inn: Optional[str]
) -> tuple[Application, owner_payouts.RegistrationCheck, Optional[str]]:
    """Сверка одной компании по ИНН. Для смены адреса ИНН — из заявки."""
    application, address, known_inn = await _load_target(db, application_id)
    inn = inn or known_inn
    if not inn:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Для первичной регистрации найдите компанию по названию и выберите её.",
        )
    try:
        check = await owner_payouts.check_registration(
            application, address.full_address, inn, _dadata(), room_number=address.room_number
        )
    except DaDataError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    if known_inn and check.inn != known_inn:
        check.warnings = (*check.warnings, f"ИНН не совпадает с компанией из заявки ({known_inn}).")
    return application, await _with_taken_warning(db, application, check), known_inn


def _check_read(check: owner_payouts.RegistrationCheck) -> RegistrationCheckRead:
    return RegistrationCheckRead(**{**check.__dict__, "warnings": list(check.warnings)})


@router.post(
    "/applications/{application_id}/registration/check", response_model=RegistrationLookupRead
)
async def check_registration(
    application_id: UUID,
    payload: RegistrationLookupRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> RegistrationLookupRead:
    """Сверка с ЕГРЮЛ без изменений (решение владельца 13.10.2026):

    - смена адреса — по ИНН компании из заявки и адресу;
    - первичная регистрация — поиск по названию (из заявки или введённому) и
      адресу: ИНН новой компании заранее неизвестен. С `inn` — проверка
      конкретного кандидата перед подтверждением.
    """
    application, address, known_inn = await _load_target(db, application_id)
    if known_inn or payload.inn:
        _, check, _ = await _run_check(db, application_id, payload.inn)
        return RegistrationLookupRead(mode="inn", candidates=[_check_read(check)], expected_inn=known_inn)

    name = (payload.name or "").strip() or owner_payouts.expected_company_name(application)
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Укажите название компании для поиска.")
    try:
        found = await owner_payouts.search_registration_by_name(
            application, address.full_address, name, _dadata(), room_number=address.room_number
        )
    except DaDataError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    found = [await _with_taken_warning(db, application, check) for check in found]
    return RegistrationLookupRead(
        mode="name",
        query=name,
        candidates=[_check_read(check) for check in found],
        expected_name=owner_payouts.expected_company_name(application),
    )


@router.post(
    "/applications/{application_id}/registration/confirm", response_model=RegistrationConfirmResult
)
async def confirm_registration(
    application_id: UUID,
    payload: RegistrationConfirmRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RegistrationConfirmResult:
    """Регистрация компании клиента подтверждена по ЕГРЮЛ (последний шаг трекера).

    Если деньги принимала площадка — выплата собственнику «к перечислению»;
    если двигать её нельзя (отменена, возврат), причина — в payout_held.
    """
    # Запрос в ЕГРЮЛ — до блокировок: сеть не должна держать строки.
    _, check, known_inn = await _run_check(db, application_id, payload.inn)

    payment_id = await _platform_payment_id(db, application_id)
    payment = await lock_payment(db, payment_id) if payment_id is not None else None
    application = await _lock_application(db, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    try:
        outcome = await owner_payouts.confirm_registration(
            db,
            application=application,
            payment=payment,
            check=check,
            accept_address_mismatch=payload.accept_address_mismatch,
            admin_id=admin.id,
            now=utcnow(),
            required_inn=known_inn,
        )
        await db.commit()
    except PayoutError as e:
        await db.rollback()
        raise _conflict(e) from e
    except IntegrityError as e:
        # Параллельная оплата/подтверждение успели завести выплату первыми.
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Выплату по заявке только что изменили — обновите реестр."
        ) from e
    return RegistrationConfirmResult(
        application_id=application.id,
        registration_confirmed_at=application.registration_confirmed_at,
        payout=await _admin_view(db, outcome.payout) if outcome.payout is not None else None,
        payout_held=outcome.payout_held,
    )


# ============================================================
# Выплата
# ============================================================


async def _lock_payout_chain(
    db: AsyncSession, payout_id: UUID
) -> tuple[OwnerPayout, Application, Payment]:
    head = await db.get(OwnerPayout, payout_id)
    if head is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Выплата не найдена")
    payment = await lock_payment(db, head.payment_id)
    application = await _lock_application(db, head.application_id)
    payout = await _lock_payout(db, payout_id)
    if payment is None or application is None or payout is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Выплата не найдена")
    return payout, application, payment


@router.post("/{payout_id}/mark-paid", response_model=AdminPayoutRead)
async def mark_paid(
    payout_id: UUID,
    payload: PayoutMarkPaidRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminPayoutRead:
    """Админ перевёл деньги собственнику в банке и отмечает это здесь."""
    payout, application, payment = await _lock_payout_chain(db, payout_id)
    try:
        await owner_payouts.mark_paid(
            db,
            payout=payout,
            application=application,
            payment=payment,
            paid_on=payload.paid_on,
            bank_reference=payload.bank_reference,
            comment=payload.comment,
            admin_id=admin.id,
            now=utcnow(),
        )
    except PayoutError as e:
        await db.rollback()
        raise _conflict(e) from e
    await db.commit()
    return await _admin_view(db, payout)


@router.post("/{payout_id}/cancel", response_model=AdminPayoutRead)
async def cancel_payout(
    payout_id: UUID,
    payload: PayoutCancelRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminPayoutRead:
    payout, _application, _payment = await _lock_payout_chain(db, payout_id)
    try:
        await owner_payouts.cancel(
            db, payout=payout, reason=payload.reason, admin_id=admin.id, now=utcnow()
        )
    except PayoutError as e:
        await db.rollback()
        raise _conflict(e) from e
    await db.commit()
    return await _admin_view(db, payout)
