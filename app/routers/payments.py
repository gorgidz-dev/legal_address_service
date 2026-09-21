from __future__ import annotations

"""HTTP endpoints для платежей.

Физлица платят через провайдера из settings.payment_provider: эквайринг Т-Банка
(боевой) или CDEK Pay (так и не включался). Юрлица — по счёту (manual_invoice).
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin, utcnow
from app.config import settings
from app.database import get_db
from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    NotificationAudience,
    PaymentAttachmentKind,
    PaymentPayerType,
    PaymentProvider,
    PaymentStatus,
    UserRole,
)
from app.models.address import Address
from app.services.application_pricing import build_price_breakdown
from app.models.application import Application
from app.models.payment import Payment
from app.models.payment_attachment import PaymentAttachment
from app.models.stored_file import StoredFile
from app.models.user import User
from app.schemas.payment import (
    PaymentAttachmentRead,
    PaymentInitiateRequest,
    PaymentManualConfirmRequest,
    PaymentRead,
    PaymentReceiptConfirm,
    PaymentRefundRequest,
    PaymentRejectRequest,
)
from app.services.cdek_pay import (
    CdekPayError,
    CdekPayNotConfigured,
    get_cdek_pay_service,
)
from app.services.notification_events import create_application_event
from app.services.tbank_acquiring import (
    TBankError,
    TBankNotConfigured,
    TBankService,
    get_tbank_service,
)
from app.services.tbank_payments import (
    MONEY_MOVING,
    NON_MONEY,
    PARTIAL_REFUNDED,
    RECHECK_INTERVAL,
    REFUND_IN_PROGRESS,
    REFUNDED,
    apply_bank_state,
    is_demo_terminal,
    lock_payment,
    may_use_test_terminal,
    recheck_payment,
    refund_failed,
)
from app.services.storage import (
    attachment_disposition,
    create_stored_file_record,
    local_stored_file_path,
    read_stored_file_async,
)

router = APIRouter(prefix="/payments", tags=["payments"])
log = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================


async def _compute_amount_kopeks(db: AsyncSession, application: Application) -> int:
    """Сумма к оплате по заявке.

    Сама формула живёт в services/application_pricing: по ней же строится
    разбивка «за что» в кабинете клиента, и две копии разошлись бы.
    """
    address = await db.get(Address, application.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")
    breakdown = build_price_breakdown(
        term_months=application.term_months,
        price_6m=address.price_6m,
        price_11m=address.price_11m,
        correspondence_price=address.correspondence_price,
        has_correspondence_service=application.has_correspondence_service,
    )
    kopeks = breakdown.to_kopeks()
    if kopeks < 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Сумма платежа должна быть не меньше 1 рубля",
        )
    return kopeks


def _assert_can_initiate(application: Application, user: User) -> None:
    if user.role != "admin" and application.created_by != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваша заявка")
    if application.status != ApplicationStatus.AWAITING_PAYMENT.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Заявка в статусе {application.status}, инициировать оплату нельзя",
        )


# ============================================================
# Т-Банк: общие хелперы
# ============================================================

_ACTIVE = (PaymentStatus.PENDING.value, PaymentStatus.AWAITING_USER.value)
# Запас после срока ссылки (RedirectDueDate): часы банка и наши могут разойтись.
_LINK_EXPIRY_GRACE = timedelta(minutes=2)
# Если после срока ссылки деньги «движутся» дольше этого — операция зависла:
# закрываем её, иначе заявка навсегда осталась бы без возможности оплаты.
_MONEY_MOVING_STALE_AFTER = timedelta(hours=1)
# Платёж в pending дольше этого — Init не завершился (упал процесс/сеть).
_STUCK_PENDING_AFTER = timedelta(minutes=10)
# Не раньше 30 секунд после создания: в первые секунды статус придёт уведомлением.
_RECHECK_MIN_AGE = timedelta(seconds=30)
# Совпадает с путём в app/routers/webhooks.py под API_PREFIX из app/main.py
# (сверяется тестом test_tbank_notification_url_matches_route).
TBANK_NOTIFICATION_PATH = "/api/v1/webhooks/tbank/notification"


def _tbank_service_or_503() -> TBankService:
    try:
        return get_tbank_service()
    except TBankNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


def _base_url() -> str:
    return settings.public_base_url.rstrip("/")


def _tbank_notification_url() -> str:
    return settings.tbank_notification_url or f"{_base_url()}{TBANK_NOTIFICATION_PATH}"


def _tbank_return_url(result: str, application_id: UUID) -> str:
    """Куда банк вернёт покупателя после формы оплаты.

    Публичная страница фронта (frontend/src/payment/PaymentReturnPage.tsx):
    с сессией на сайте она сразу ведёт в карточку заявки, где идёт проверка
    оплаты, а в мобильной вкладке без сессии просит вернуться в приложение.
    Страница только показывает текст — оплату засчитывает бэкенд по банку,
    поэтому подделать «успех» адресом возврата нельзя.
    """
    override = settings.tbank_success_url if result == "success" else settings.tbank_fail_url
    if override:
        return override
    return f"{_base_url()}/payment/{result}?application={application_id}"


def _assert_may_pay_on_terminal(service: TBankService, user: User) -> None:
    if service.is_demo and not may_use_test_terminal(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Онлайн-оплата работает в тестовом режиме. Чтобы оплатить заявку, напишите в поддержку.",
        )


def _foreign_terminal(payment: Payment, service: TBankService) -> bool:
    """Платёж создан на другом терминале — текущий о нём ничего не знает."""
    return bool(payment.provider_account) and payment.provider_account != service.terminal_key


def _close_foreign_locally(payment: Payment, closed: PaymentStatus) -> None:
    """Закрыть у себя платёж чужого терминала — но только DEMO.

    Ссылка боевого терминала после смены ключа у банка жива и оплачиваема, а
    её уведомления мы больше не принимаем (чужой TerminalKey): закрыть её молча
    значило бы потерять настоящие деньги. Такое — только руками, через ЛК.
    """
    if not is_demo_terminal(payment.provider_account):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Платёж проведён на другом боевом терминале Т-Банка — разберитесь в его ЛК.",
        )
    payment.status = closed.value


def _tbank_link_dead(payment: Payment, now: datetime) -> bool:
    """Ссылку на оплату пора заменить новой (у активного платежа Т-Банка)."""
    if payment.provider != PaymentProvider.TBANK.value or payment.status not in _ACTIVE:
        return False
    if payment.status == PaymentStatus.PENDING.value:
        return now - payment.created_at > _STUCK_PENDING_AFTER
    return payment.expires_at is not None and now > payment.expires_at + _LINK_EXPIRY_GRACE


async def _find_active_payment(db: AsyncSession, application_id: UUID) -> Optional[Payment]:
    result = await db.execute(
        select(Payment)
        .where(
            Payment.application_id == application_id,
            Payment.status.in_(list(_ACTIVE)),
        )
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _close_unpaid_link(
    db: AsyncSession,
    service: TBankService,
    locked: Payment,
    bank_status: str,
    *,
    closed: PaymentStatus,
) -> None:
    """Закрыть в банке ссылку, по которой (по GetState) денег нет. Вызывается под блокировкой.

    Ответ Cancel — это состояние банка, его прогоняем через автомат: если
    покупатель успел оплатить, Cancel у банка стал возвратом, и платёж честно
    становится «оплачен и возвращается», а не «отменён».
    """
    try:
        result = await service.cancel(payment_id=locked.provider_payment_id)
    except TBankError as e:
        if e.is_business_refusal and bank_status in NON_MONEY:
            # Банк не отменяет из этого статуса (из AUTH_FAIL/3DS_CHECKING
            # Cancel не описан), но денег по платежу нет — закрываем у себя.
            locked.status = closed.value
            return
        # Исход неизвестен (сеть/сбой) — Cancel мог и пройти. Уточняем.
        try:
            state = await service.get_state(payment_id=locked.provider_payment_id)
            await apply_bank_state(
                db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks,
                voided_as=closed,
            )
        except TBankError:
            pass
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Т-Банк не ответил на закрытие ссылки. Повторите через минуту.",
        ) from e
    await apply_bank_state(
        db, payment=locked, status=result.status, amount_kopeks=None, voided_as=closed
    )
    if locked.status in _ACTIVE:
        # Неожиданный ответ банка: ссылку не закрыли. Сохраняем что знаем.
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Т-Банк ответил на закрытие ссылки статусом «{result.status}». Повторите позже.",
        )


async def _retire_dead_tbank_payment(db: AsyncSession, payment: Payment) -> Optional[Payment]:
    """Разобраться с просроченной ссылкой, прежде чем выдать новую.

    Возвращает платёж, который надо отдать клиенту вместо новой ссылки
    (оплачен, оплата идёт прямо сейчас, или новую уже выдал параллельный
    запрос), либо None — старый закрыт, можно выдавать новую.
    """
    service = _tbank_service_or_503()
    if payment.provider_payment_id is None:
        payment.status = PaymentStatus.EXPIRED.value  # Init не ответил — ссылку не видели
        await db.flush()
        return None
    if _foreign_terminal(payment, service):
        _close_foreign_locally(payment, PaymentStatus.EXPIRED)
        await db.flush()
        return None

    application_id = payment.application_id
    locked = await lock_payment(db, payment.id) or payment
    if locked.status not in _ACTIVE:
        # Параллельный запрос уже разобрался со старой ссылкой.
        if locked.status == PaymentStatus.SUCCEEDED.value:
            return locked
        return await _find_active_payment(db, application_id)

    try:
        state = await service.get_state(payment_id=locked.provider_payment_id)
    except TBankError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Не удалось проверить прошлую ссылку на оплату в Т-Банке. Повторите через минуту.",
        ) from e
    await apply_bank_state(
        db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks,
        voided_as=PaymentStatus.EXPIRED,
    )
    locked.provider_checked_at = utcnow()
    if locked.status == PaymentStatus.SUCCEEDED.value:
        await db.commit()
        await db.refresh(locked)
        return locked
    if locked.status not in _ACTIVE:
        await db.flush()  # закрыт (отказ, истёк, «оплачен и возвращается») — место свободно
        return None
    if state.status == "CONFIRMED":
        # Банк показывает оплату, но сумма не совпала: Cancel сейчас был бы
        # ВОЗВРАТОМ — такое решает человек, не автоматика. Админ уже извещён.
        await db.commit()
        await db.refresh(locked)
        return locked
    stale = locked.expires_at is not None and utcnow() > locked.expires_at + _MONEY_MOVING_STALE_AFTER
    if state.status in MONEY_MOVING and not stale:
        # Покупатель платит прямо сейчас — новую ссылку не даём, ждём исхода.
        await db.commit()
        await db.refresh(locked)
        return locked
    if state.status not in NON_MONEY and state.status not in MONEY_MOVING:
        # Статус, которого нет в справочнике: Cancel мог бы оказаться возвратом.
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Т-Банк показывает по прошлой ссылке статус «{state.status}». "
            "Напишите в поддержку — разберёмся вручную.",
        )

    await _close_unpaid_link(db, service, locked, state.status, closed=PaymentStatus.EXPIRED)
    await db.flush()
    return None


async def _initiate_tbank(db: AsyncSession, application: Application, user: User) -> Payment:
    service = _tbank_service_or_503()
    _assert_may_pay_on_terminal(service, user)

    amount_kopeks = await _compute_amount_kopeks(db, application)
    redirect_due = utcnow() + timedelta(minutes=settings.tbank_link_ttl_minutes)
    # После rollback все объекты сессии устаревают, и чтение application.id
    # полезло бы в базу синхронно (MissingGreenlet) — запоминаем заранее.
    application_id = application.id
    payment = Payment(
        application_id=application_id,
        provider=PaymentProvider.TBANK.value,
        payer_type=PaymentPayerType.INDIVIDUAL.value,
        status=PaymentStatus.PENDING.value,
        amount_kopeks=amount_kopeks,
        currency="RUR",
        pay_for=_pay_for_label(application),
        provider_account=service.terminal_key,
        initiated_by=user.id,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError:
        # Второе одновременное «Оплатить»: уникальный индекс пустил только один
        # активный платёж — отдаём его, а не создаём второй.
        await db.rollback()
        existing = await _find_active_payment(db, application_id)
        if existing is not None:
            return existing
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Платёж по заявке уже создаётся — обновите страницу."
        )

    try:
        result = await service.init(
            amount_kopeks=amount_kopeks,
            order_id=str(payment.id),
            description=payment.pay_for,
            notification_url=_tbank_notification_url(),
            success_url=_tbank_return_url("success", application_id),
            fail_url=_tbank_return_url("fail", application_id),
            redirect_due=redirect_due,
        )
    except TBankError as e:
        payment.status = PaymentStatus.FAILED.value
        payment.provider_status = f"INIT_ERROR:{e.error_code}" if e.error_code else "INIT_ERROR"
        await db.commit()
        # Этот текст видит покупатель — технические подробности только в лог.
        log.warning("T-Bank Init failed for payment %s: %s", payment.id, e)
        if e.is_business_refusal:
            detail = (
                f"Банк не принял платёж (код {e.error_code}). Напишите в поддержку — "
                "поможем оплатить."
            )
        else:
            detail = "Банк сейчас не отвечает. Попробуйте ещё раз через минуту."
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail) from e

    payment.status = PaymentStatus.AWAITING_USER.value
    payment.provider_payment_id = result.payment_id
    payment.payment_url = result.payment_url
    payment.provider_status = result.status
    payment.expires_at = redirect_due
    await db.commit()
    await db.refresh(payment)
    return payment


def _needs_tbank_recheck(payment: Payment, now: datetime) -> bool:
    if payment.provider != PaymentProvider.TBANK.value or not payment.provider_payment_id:
        return False
    if payment.status not in {
        PaymentStatus.AWAITING_USER.value,
        PaymentStatus.REFUND_REQUESTED.value,  # возврат по СБП асинхронный
    }:
        return False
    if now - payment.created_at < _RECHECK_MIN_AGE:
        return False
    checked = payment.provider_checked_at
    return checked is None or now - checked >= RECHECK_INTERVAL


def _masked_for(payment: Payment, may_see_demo: bool):
    """Ссылку DEMO-терминала видят только тестировщики и админы.

    Иначе её, выданную админу, мог бы взять владелец заявки через GET и
    оплатить тестовой картой. (Заявку это всё равно не оплатит — _on_paid
    проверяет инициатора, — но ссылку незачем и показывать.)

    Право (may_use_test_terminal) вычисляется в начале запроса: после rollback
    объект пользователя устаревает, и чтение user.role полезло бы в базу
    синхронно — MissingGreenlet (поймано смоуком на двойном «Оплатить»).
    """
    if (
        payment.provider == PaymentProvider.TBANK.value
        and payment.payment_url
        and is_demo_terminal(payment.provider_account)
        and not may_see_demo
    ):
        return PaymentRead.model_validate(payment).model_copy(update={"payment_url": None})
    return payment


# ============================================================
# Endpoints
# ============================================================


@router.post(
    "/initiate",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_payment(
    payload: PaymentInitiateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Payment:
    may_see_demo = may_use_test_terminal(user)  # до запросов: после rollback user устареет
    return _masked_for(await _initiate(db, payload, user), may_see_demo)


async def _initiate(db: AsyncSession, payload: PaymentInitiateRequest, user: User) -> Payment:
    application = await db.get(Application, payload.application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    _assert_can_initiate(application, user)

    # Уже есть активный платёж (pending/awaiting_user) — отдаём его, не создаём дубль.
    # Это покрывает и manual_invoice (создан вместе с заявкой), и повторный клик.
    # Исключение — просроченная ссылка Т-Банка: её закрываем и выдаём новую.
    active = await _find_active_payment(db, application.id)
    if active is not None:
        dead = _tbank_link_dead(active, utcnow())
        if active.provider == PaymentProvider.TBANK.value:
            try:
                service = get_tbank_service()
            except TBankNotConfigured:
                service = None  # терминал отключён — судить о ссылке не по чему
            if service is not None:
                # Гард DEMO-терминала и для уже выданной ссылки: её мог получить
                # админ или тестировщик, а оплатить тестовой картой — владелец заявки.
                _assert_may_pay_on_terminal(service, user)
                # Ссылка с другого терминала (DEMO до перехода на боевой) мертва сразу.
                dead = dead or _foreign_terminal(active, service)
        if not dead:
            return active
        still_open = await _retire_dead_tbank_payment(db, active)
        if still_open is not None:
            return still_open

    if settings.payment_provider == PaymentProvider.TBANK.value:
        return await _initiate_tbank(db, application, user)
    return await _initiate_cdek(db, application, payload, user)


async def _initiate_cdek(
    db: AsyncSession,
    application: Application,
    payload: PaymentInitiateRequest,
    user: User,
) -> Payment:
    amount_kopeks = await _compute_amount_kopeks(db, application)
    pay_for = _pay_for_label(application)

    try:
        service = get_cdek_pay_service()
    except CdekPayNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    application_id = application.id  # см. _initiate_tbank: после rollback объекты устаревают
    payment = Payment(
        application_id=application_id,
        provider=PaymentProvider.CDEK_PAY.value,
        payer_type=payload.payer_type.value,
        status=PaymentStatus.PENDING.value,
        amount_kopeks=amount_kopeks,
        currency=service.currency,
        pay_for=pay_for,
        initiated_by=user.id,
    )
    db.add(payment)
    try:
        await db.flush()
    except IntegrityError:
        # Двойной клик упёрся в ux_payments_one_active_per_application.
        await db.rollback()
        existing = await _find_active_payment(db, application_id)
        if existing is not None:
            return existing
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Платёж по заявке уже создаётся — обновите страницу."
        )

    try:
        qr = await service.generate_sbp_qr(
            amount_kopeks=amount_kopeks,
            pay_for=pay_for,
            qr_life_time_minutes=settings.cdek_qr_life_time_minutes,
            user_phone=_only_ru_phone_digits(payload.user_phone or application.contact_phone),
            user_email=payload.user_email or application.contact_email,
            return_url_success=settings.cdek_return_success_url or None,
            return_url_fail=settings.cdek_return_fail_url or None,
            pay_for_details={"application_id": str(application.id), "payment_id": str(payment.id)},
        )
    except CdekPayError as e:
        # Откатываем pending-платёж — пусть пользователь ретрайнет.
        payment.status = PaymentStatus.FAILED.value
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"CDEK Pay: {e}") from e

    payment.status = PaymentStatus.AWAITING_USER.value
    payment.cdek_access_key = qr.access_key
    payment.cdek_order_id = qr.order_id
    payment.qr_link = qr.qr_link
    payment.qr_image_base64 = qr.qr_image_base64
    payment.expires_at = utcnow() + timedelta(minutes=settings.cdek_qr_life_time_minutes)

    await db.commit()
    await db.refresh(payment)
    return payment


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Payment:
    may_see_demo = may_use_test_terminal(user)
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if user.role != "admin":
        application = await db.get(Application, payment.application_id)
        if application is None or application.created_by != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваш платёж")
    if _needs_tbank_recheck(payment, utcnow()):
        payment = await recheck_payment(db, payment)
    return _masked_for(payment, may_see_demo)


@router.post("/{payment_id}/cancel", response_model=PaymentRead)
async def cancel_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Payment:
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if payment.status not in {
        PaymentStatus.PENDING.value,
        PaymentStatus.AWAITING_USER.value,
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Отменить можно только pending/awaiting_user; статус: {payment.status}",
        )
    if payment.provider == PaymentProvider.TBANK.value and payment.provider_payment_id:
        return await _cancel_tbank(db, payment)
    if payment.cdek_access_key:
        try:
            service = get_cdek_pay_service()
            await service.block_payment_link(access_key=payment.cdek_access_key)
        except (CdekPayNotConfigured, CdekPayError):
            # Не валим запрос — просто переводим в cancelled у себя.
            pass
    payment.status = PaymentStatus.CANCELLED.value
    await db.commit()
    await db.refresh(payment)
    return payment


@router.post("/{payment_id}/mark-paid", response_model=PaymentRead)
async def mark_payment_paid(
    payment_id: UUID,
    payload: PaymentManualConfirmRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Payment:
    """Ручное подтверждение оплаты для provider=manual_invoice (юр.лица).

    SBP-платежи (cdek_pay) подтверждаются автоматически через webhook —
    их сюда пропускать нельзя.
    """
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if payment.provider != PaymentProvider.MANUAL_INVOICE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "mark-paid доступен только для manual_invoice; cdek_pay подтверждается callback'ом",
        )
    if payment.status not in {
        PaymentStatus.PENDING.value,
        PaymentStatus.AWAITING_USER.value,
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Подтвердить можно только pending/awaiting_user; статус: {payment.status}",
        )

    payment.status = PaymentStatus.SUCCEEDED.value
    payment.paid_at = utcnow()

    application = await db.get(Application, payment.application_id)
    if application is not None and application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        application.status = ApplicationStatus.PAID.value
        comment_suffix = f" Комментарий: {payload.comment}" if payload.comment else ""
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=NotificationAudience.CLIENT,
            title="Оплата подтверждена",
            message=(
                "Администратор подтвердил поступление оплаты по счёту. "
                "Заявка передана на проверку."
                + comment_suffix
            ),
            payload={
                "status": ApplicationStatus.PAID.value,
                "payment_id": str(payment.id),
                "confirmed_by": str(admin.id),
            },
            created_by=admin.id,
        )

    await db.commit()
    await db.refresh(payment)
    return payment


@router.post("/{payment_id}/reject-payment", response_model=PaymentRead)
async def reject_manual_payment(
    payment_id: UUID,
    payload: PaymentRejectRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Payment:
    """Админ помечает manual_invoice платёж как не оплаченный (failed)."""
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if payment.provider != PaymentProvider.MANUAL_INVOICE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "reject-payment доступен только для manual_invoice",
        )
    if payment.status not in {
        PaymentStatus.PENDING.value,
        PaymentStatus.AWAITING_USER.value,
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Отклонить можно только pending/awaiting_user; статус: {payment.status}",
        )

    payment.status = PaymentStatus.FAILED.value
    payment.last_callback_payload = {
        "rejected_by_admin": str(admin.id),
        "reason": payload.reason,
    }

    application = await db.get(Application, payment.application_id)
    if application is not None and application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=NotificationAudience.CLIENT,
            title="Оплата не подтверждена",
            message=(
                "Администратор не подтвердил оплату по счёту. "
                f"Причина: {payload.reason}. Свяжитесь с поддержкой."
            ),
            payload={"payment_id": str(payment.id), "reason": payload.reason},
            created_by=admin.id,
        )

    await db.commit()
    await db.refresh(payment)
    return payment


@router.post("/{payment_id}/refund", response_model=PaymentRead)
async def refund_payment(
    payment_id: UUID,
    payload: PaymentRefundRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Payment:
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if payment.provider == PaymentProvider.TBANK.value:
        return await _refund_tbank(db, payment, payload)
    if payment.status != PaymentStatus.SUCCEEDED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Возврат возможен только из succeeded; статус: {payment.status}",
        )
    if payment.cdek_payment_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "У платежа отсутствует cdek_payment_id (нет callback от CDEK)",
        )
    refund_amount = payload.value_refund_kopeks or payment.amount_kopeks
    if refund_amount > payment.amount_kopeks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Сумма возврата больше суммы платежа",
        )

    try:
        service = get_cdek_pay_service()
        await service.request_refund(
            payment_id=payment.cdek_payment_id,
            value_refund_kopeks=refund_amount,
            reason=payload.reason,
        )
    except CdekPayNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except CdekPayError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"CDEK Pay: {e}") from e

    payment.status = PaymentStatus.REFUND_REQUESTED.value
    await db.commit()
    await db.refresh(payment)
    return payment


async def _cancel_tbank(db: AsyncSession, payment: Payment) -> Payment:
    """Отмена неоплаченного платежа Т-Банка админом.

    Всё под блокировкой строки и по состоянию банка (GetState): Cancel по
    оплаченному у банка платежу — это ВОЗВРАТ, поэтому оплаченный (в том числе с
    несовпавшей суммой) не отменяем, а платящийся прямо сейчас — просим подождать.
    """
    service = _tbank_service_or_503()
    locked = await lock_payment(db, payment.id) or payment
    if locked.status not in _ACTIVE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Платёж уже в статусе {locked.status} — отменять нечего."
        )
    if _foreign_terminal(locked, service):
        _close_foreign_locally(locked, PaymentStatus.CANCELLED)
        await db.commit()
        await db.refresh(locked)
        return locked

    try:
        state = await service.get_state(payment_id=locked.provider_payment_id)
    except TBankError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    await apply_bank_state(
        db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks,
        voided_as=PaymentStatus.CANCELLED,
    )
    locked.provider_checked_at = utcnow()
    if locked.status not in _ACTIVE:
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Платёж уже в статусе {locked.status} (банк: {state.status}) — отменять нечего. "
            "Если он оплачен, оформите возврат.",
        )
    if state.status == "CONFIRMED":
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Т-Банк показывает оплату с суммой, не совпавшей с заказом. Отмена была бы "
            "возвратом — разберитесь в ЛК Т-Бизнеса.",
        )
    if state.status in MONEY_MOVING:
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Покупатель прямо сейчас платит (статус банка {state.status}). Повторите позже.",
        )
    if state.status not in NON_MONEY:
        # Статус, которого нет в справочнике: Cancel мог бы оказаться возвратом.
        await db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Т-Банк показывает статус «{state.status}» — отмену сделайте в ЛК Т-Бизнеса.",
        )
    await _close_unpaid_link(db, service, locked, state.status, closed=PaymentStatus.CANCELLED)
    await db.commit()
    await db.refresh(locked)
    return locked


async def _refund_tbank(
    db: AsyncSession, payment: Payment, payload: PaymentRefundRequest
) -> Payment:
    """Полный возврат по оплаченному платежу Т-Банка.

    Только полный: у уведомлений о возврате нет id операции, и несколько
    частичных банк описывает неотличимо — частичные делают в ЛК Т-Бизнеса (там
    же банк сам соберёт чек). Каждая попытка — свой ExternalRequestId
    refund:<id>:<попытка>; повтор незавершённой попытки идёт ТЕМ ЖЕ ключом, и
    банк не исполнит её дважды. Новая попытка — только после окончательного
    отказа банка. Всё под блокировкой строки: второй клик ждёт первый.
    """
    service = _tbank_service_or_503()
    locked = await lock_payment(db, payment.id) or payment
    if not locked.provider_payment_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "У платежа нет PaymentId Т-Банка")
    if _foreign_terminal(locked, service):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Платёж проведён на другом терминале Т-Банка — возврат оформите в его ЛК.",
        )
    if payload.value_refund_kopeks not in (None, locked.amount_kopeks):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Через систему — только полный возврат. Частичный оформите в ЛК Т-Бизнеса.",
        )
    if (locked.refunded_kopeks or 0) > 0 or locked.provider_status == PARTIAL_REFUNDED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "По платежу уже был частичный возврат в ЛК — остаток тоже возвращайте в ЛК.",
        )

    if locked.status == PaymentStatus.SUCCEEDED.value:
        locked.refund_attempts = (locked.refund_attempts or 0) + 1
        locked.refund_key = f"refund:{locked.id}:{locked.refund_attempts}"
        locked.status = PaymentStatus.REFUND_REQUESTED.value
    elif locked.status == PaymentStatus.REFUND_REQUESTED.value and locked.refund_key:
        pass  # повтор незавершённой попытки — тем же ключом
    elif locked.status == PaymentStatus.REFUND_REQUESTED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Возврат уже в обработке у банка (запущен из ЛК Т-Бизнеса или при закрытии "
            "ссылки) — статус обновится сам.",
        )
    else:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Возврат возможен только по оплаченному платежу; статус: {locked.status}",
        )

    try:
        result = await service.cancel(
            payment_id=locked.provider_payment_id,
            external_request_id=locked.refund_key,  # без Amount — всё, и чек возврата от банка
        )
    except TBankError as e:
        if e.is_business_refusal:
            # Отказ — но не идёт ли уже возврат (например, это повтор)? Спросим.
            try:
                state = await service.get_state(payment_id=locked.provider_payment_id)
            except TBankError:
                state = None
            if state is not None and state.status in REFUND_IN_PROGRESS | {REFUNDED}:
                await apply_bank_state(
                    db, payment=locked, status=state.status, amount_kopeks=state.amount_kopeks
                )
                await db.commit()
                await db.refresh(locked)
                return locked
            if state is not None and state.status == "CONFIRMED":
                # Отказ окончательный: банк по-прежнему показывает оплату без возврата.
                await refund_failed(db, locked, reason=f"Т-Банк отказал в возврате ({e})")
                await db.commit()
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
            # Состояние не подтвердилось — не объявляем отказ наугад: попытка
            # остаётся «в пути», повтор тем же ключом безопасен.
            await db.commit()
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"{e}. Состояние возврата не подтвердилось — повторите позже.",
            ) from e
        # Сеть или сбой банка: исход неизвестен. Возврат остаётся «в пути» с тем
        # же ключом — повтор безопасен, банк не исполнит попытку дважды.
        await db.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Т-Банк не ответил — неизвестно, прошёл ли возврат. Повторите: повтор "
            "безопасен, дважды банк не вернёт.",
        ) from e

    await apply_bank_state(db, payment=locked, status=result.status, amount_kopeks=None)
    await db.commit()
    await db.refresh(locked)
    return locked


# ============================================================
# Payment attachments — счёт (owner) и платёжка (client)
# ============================================================


async def _load_payment_ctx(
    db: AsyncSession, payment_id: UUID
) -> tuple[Payment, Application, Address]:
    """Грузит payment + application + address. 404 если чего-то нет."""
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    application = await db.get(Application, payment.application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка платежа не найдена")
    address = await db.get(Address, application.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")
    return payment, application, address


def _payment_role(
    user: User, application: Application, address: Address
) -> str | None:
    """Роль пользователя относительно платежа: client | owner | staff | None."""
    role = user.role
    if role in (UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.LAWYER.value):
        return "staff"
    if role == UserRole.CLIENT.value and application.created_by == user.id:
        return "client"
    if (
        role == UserRole.OWNER.value
        and user.provider_id is not None
        and user.provider_id == address.provider_id
    ):
        return "owner"
    return None


def _payment_attachment_read(
    att: PaymentAttachment, file: StoredFile
) -> PaymentAttachmentRead:
    return PaymentAttachmentRead(
        id=att.id,
        payment_id=att.payment_id,
        kind=PaymentAttachmentKind(att.kind),
        original_filename=file.original_filename,
        size_bytes=file.size_bytes,
        uploaded_by=att.uploaded_by,
        created_at=att.created_at,
        download_url=f"/payments/{att.payment_id}/attachments/{att.id}/download",
    )


@router.get("/by-application/{application_id}", response_model=Optional[PaymentRead])
async def get_payment_by_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Optional[Payment]:
    """Платёж по заявке (read-only) — или null.

    Нужен собственнику/админу: они не создают платёж (как initiate), а только
    смотрят существующий. Доступ: клиент заявки, собственник адреса, staff.
    """
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    address = await db.get(Address, application.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")
    if _payment_role(user, application, address) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этой заявке")
    payment = (
        await db.execute(
            select(Payment)
            .where(Payment.application_id == application_id)
            .order_by(Payment.created_at.desc())
        )
    ).scalars().first()
    return None if payment is None else _masked_for(payment, may_use_test_terminal(user))


@router.post(
    "/{payment_id}/attachments",
    response_model=PaymentAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_payment_attachment(
    payment_id: UUID,
    file: UploadFile = File(...),
    kind: PaymentAttachmentKind = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentAttachmentRead:
    """Загрузка документа платежа.

    kind=invoice       — счёт; грузит собственник адреса.
    kind=payment_order — платёжка; грузит клиент (действие «я оплатил»).
    Только для provider=manual_invoice (cdek_pay подтверждается автоматически).
    """
    payment, application, address = await _load_payment_ctx(db, payment_id)
    if payment.provider != PaymentProvider.MANUAL_INVOICE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Документы платежа доступны только для оплаты по счёту (manual_invoice)",
        )

    role = _payment_role(user, application, address)
    if kind == PaymentAttachmentKind.INVOICE and role != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Счёт загружает собственник адреса"
        )
    if kind == PaymentAttachmentKind.PAYMENT_ORDER and role != "client":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Платёжное поручение загружает клиент по своей заявке",
        )
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому платежу")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл пустой")

    file_record = await create_stored_file_record(
        db=db,
        content=content,
        kind=f"payment_{kind.value}",
        original_filename=file.filename or kind.value,
        content_type=file.content_type or "application/octet-stream",
        application_id=application.id,
        uploaded_by=user.id,
    )
    attachment = PaymentAttachment(
        payment_id=payment.id,
        kind=kind.value,
        file_id=file_record.id,
        uploaded_by=user.id,
    )
    db.add(attachment)

    # Платёжку загрузил клиент → событие для собственника («я оплатил»).
    if kind == PaymentAttachmentKind.PAYMENT_ORDER:
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.COMMENT_ADDED,
            audience=NotificationAudience.OWNER,
            title="Клиент сообщил об оплате",
            message=(
                "Клиент загрузил платёжное поручение по счёту. "
                "Проверьте поступление средств и подтвердите."
            ),
            payload={"payment_id": str(payment.id)},
            created_by=user.id,
        )
    await db.commit()
    await db.refresh(attachment)
    await db.refresh(file_record)
    return _payment_attachment_read(attachment, file_record)


@router.get(
    "/{payment_id}/attachments", response_model=list[PaymentAttachmentRead]
)
async def list_payment_attachments(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PaymentAttachmentRead]:
    payment, application, address = await _load_payment_ctx(db, payment_id)
    if _payment_role(user, application, address) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому платежу")
    rows = (
        await db.execute(
            select(PaymentAttachment, StoredFile)
            .join(StoredFile, StoredFile.id == PaymentAttachment.file_id)
            .where(PaymentAttachment.payment_id == payment_id)
            .order_by(PaymentAttachment.created_at.asc())
        )
    ).all()
    return [_payment_attachment_read(att, file) for att, file in rows]


@router.get(
    "/{payment_id}/attachments/{attachment_id}/download", response_model=None
)
async def download_payment_attachment(
    payment_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    payment, application, address = await _load_payment_ctx(db, payment_id)
    if _payment_role(user, application, address) is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к этому платежу")
    attachment = await db.get(PaymentAttachment, attachment_id)
    if attachment is None or attachment.payment_id != payment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    file_record = await db.get(StoredFile, attachment.file_id)
    if file_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл не найден")
    try:
        local_path = local_stored_file_path(file_record)
        if local_path is not None:
            return FileResponse(
                local_path,
                filename=file_record.original_filename,
                media_type=file_record.content_type,
            )
        return Response(
            content=await read_stored_file_async(file_record),
            media_type=file_record.content_type,
            headers={
                "Content-Disposition": attachment_disposition(file_record.original_filename)
            },
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


@router.post("/{payment_id}/confirm-receipt", response_model=PaymentRead)
async def confirm_payment_receipt(
    payment_id: UUID,
    payload: PaymentReceiptConfirm,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Payment:
    """Собственник подтверждает поступление средств по счёту.

    Это и есть «момент оплаты» в manual_invoice-флоу: payment → succeeded,
    заявка awaiting_payment → paid. Дальше собственник готовит документы.
    """
    payment, application, address = await _load_payment_ctx(db, payment_id)
    if payment.provider != PaymentProvider.MANUAL_INVOICE.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "confirm-receipt доступен только для оплаты по счёту (manual_invoice)",
        )
    if _payment_role(user, application, address) != "owner":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Подтвердить поступление средств может только собственник адреса",
        )
    if payment.status not in {
        PaymentStatus.PENDING.value,
        PaymentStatus.AWAITING_USER.value,
    }:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Подтвердить можно только pending/awaiting_user; статус: {payment.status}",
        )

    payment.status = PaymentStatus.SUCCEEDED.value
    payment.paid_at = utcnow()
    if application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        application.status = ApplicationStatus.PAID.value
        comment_suffix = f" Комментарий: {payload.comment}" if payload.comment else ""
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=NotificationAudience.CLIENT,
            title="Оплата подтверждена",
            message=(
                "Собственник подтвердил поступление средств по счёту. "
                "Заявка переходит к подготовке документов." + comment_suffix
            ),
            payload={
                "status": ApplicationStatus.PAID.value,
                "payment_id": str(payment.id),
                "confirmed_by": str(user.id),
            },
            created_by=user.id,
        )
    await db.commit()
    await db.refresh(payment)
    return payment


# ============================================================
# Helpers
# ============================================================


def _pay_for_label(application: Application) -> str:
    name = application.company_name or application.planned_client_name or "Юридический адрес"
    base = f"Юр. адрес: {name}".strip()
    return base[:100]  # CDEK ограничивает 100 символов


def _only_ru_phone_digits(phone: Optional[str]) -> Optional[str]:
    """CDEK ждёт ровно 11 цифр (7XXXXXXXXXX или 8XXXXXXXXXX). Берём наш E.164 и режем."""
    if not phone:
        return None
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return None
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return digits
    if len(digits) == 10:
        return "7" + digits
    return None


# ============================================================
# Webhook handler (public — see _is_public_path in app/main.py)
# ============================================================


async def handle_cdek_pay_payment_callback(
    *,
    db: AsyncSession,
    body: dict,
) -> None:
    """Обрабатывает payment_callback от CDEK Pay.

    Идемпотентно: повторный callback с тем же payment.id вернёт без записи.
    Подпись должна быть валидирована в роутере (он знает secret_key).
    """
    payment_section = body.get("payment") or {}
    access_key = payment_section.get("access_key")
    cdek_payment_id = payment_section.get("id")
    if not access_key or cdek_payment_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неполный payload payment")

    result = await db.execute(
        select(Payment).where(Payment.cdek_access_key == access_key)
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        # Нет нашего ордера — игнор, чтобы CDEK не ретраил вечно.
        return

    if payment.status == PaymentStatus.SUCCEEDED.value and payment.cdek_payment_id == cdek_payment_id:
        # Идемпотентность: уже обработано.
        return

    payment.status = PaymentStatus.SUCCEEDED.value
    payment.cdek_payment_id = int(cdek_payment_id)
    payment.paid_at = utcnow()
    payment.last_callback_payload = body

    application = await db.get(Application, payment.application_id)
    if application is not None and application.status == ApplicationStatus.AWAITING_PAYMENT.value:
        application.status = ApplicationStatus.PAID.value
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=NotificationAudience.CLIENT,
            title="Оплата получена",
            message="Заявка переведена в статус «Оплачена» и ушла на проверку.",
            payload={"status": ApplicationStatus.PAID.value, "payment_id": str(payment.id)},
            created_by=None,
        )
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.STATUS_CHANGED,
            audience=NotificationAudience.ADMIN,
            title="Поступила оплата",
            message=f"Платёж {payment.amount_kopeks // 100} ₽ подтверждён CDEK Pay.",
            payload={"status": ApplicationStatus.PAID.value, "payment_id": str(payment.id)},
            created_by=None,
        )

    await db.commit()


async def handle_cdek_pay_refund_callback(
    *,
    db: AsyncSession,
    body: dict,
) -> None:
    payment_section = body.get("payment") or {}
    access_key = payment_section.get("access_key")
    if not access_key:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неполный payload refund")
    result = await db.execute(
        select(Payment).where(Payment.cdek_access_key == access_key)
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        return
    if payment.status == PaymentStatus.REFUNDED.value:
        return
    payment.status = PaymentStatus.REFUNDED.value
    payment.refunded_at = utcnow()
    payment.last_callback_payload = body
    await db.commit()
