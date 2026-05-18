from __future__ import annotations

"""HTTP endpoints для платежей. На MVP — CDEK Pay SBP для физлиц."""
from datetime import timedelta
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
from app.services.storage import (
    create_stored_file_record,
    local_stored_file_path,
    read_stored_file_async,
)

router = APIRouter(prefix="/payments", tags=["payments"])


# ============================================================
# Helpers
# ============================================================


async def _compute_amount_kopeks(db: AsyncSession, application: Application) -> int:
    """Сумма к оплате по заявке: цена за выбранный срок + корреспонденция (если включена)."""
    address = await db.get(Address, application.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")
    term = application.term_months or 11
    base: Decimal = address.price_6m if term == 6 else address.price_11m
    total = base
    if application.has_correspondence_service and address.correspondence_price is not None:
        total += address.correspondence_price
    kopeks = int((total * 100).quantize(Decimal("1")))
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
    application = await db.get(Application, payload.application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    _assert_can_initiate(application, user)

    # Если уже есть активный платёж (pending/awaiting_user) — возвращаем его, не создаём дубль.
    # Это покрывает и manual_invoice (создан в create) и cdek_pay (повторный клик кнопки).
    existing = await db.execute(
        select(Payment)
        .where(
            Payment.application_id == application.id,
            Payment.status.in_(
                [PaymentStatus.PENDING.value, PaymentStatus.AWAITING_USER.value]
            ),
        )
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    active = existing.scalar_one_or_none()
    if active is not None:
        # Для manual_invoice initiate ничего не делает — платёж уже создан,
        # ждёт счёта от собственника и ручного подтверждения.
        return active

    amount_kopeks = await _compute_amount_kopeks(db, application)
    pay_for = _pay_for_label(application)

    try:
        service = get_cdek_pay_service()
    except CdekPayNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    payment = Payment(
        application_id=application.id,
        provider=PaymentProvider.CDEK_PAY.value,
        payer_type=payload.payer_type.value,
        status=PaymentStatus.PENDING.value,
        amount_kopeks=amount_kopeks,
        currency=service.currency,
        pay_for=pay_for,
        initiated_by=user.id,
    )
    db.add(payment)
    await db.flush()

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
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Платёж не найден")
    if user.role != "admin":
        application = await db.get(Application, payment.application_id)
        if application is None or application.created_by != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Это не ваш платёж")
    return payment


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
    return payment


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
                "Content-Disposition": (
                    f'attachment; filename="{file_record.original_filename}"'
                )
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
