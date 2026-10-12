from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    DocumentFileKind,
    NotificationAudience,
    UserRole,
)
from app.models.application import Application
from app.models.stored_file import StoredFile
from app.models.user import User
from app.schemas.application_document import (
    ApplicationDocumentModerationRead,
    ApplicationDocumentRead,
    ApplicationDocumentUploadResult,
)
from app.services.application_workflow import next_actions_for_status, workflow_role_for_user
from app.services.application_sla import apply_sla
from app.services.notification_events import create_application_event
from app.services.chat_attachments import content_type_for, ensure_within_limits
from app.services.storage import create_stored_file_record


OWNER_UPLOAD_KINDS = {
    DocumentFileKind.CONTRACT,
    DocumentFileKind.ACT,
    DocumentFileKind.OWNER_CONSENT,
    DocumentFileKind.POSTAL_SERVICE,
    DocumentFileKind.OWNERSHIP_PROOF,
    DocumentFileKind.GUARANTEE_LETTER,
}

OWNER_UPLOAD_STATUSES = {
    ApplicationStatus.DOCUMENTS_PREPARING.value,
    ApplicationStatus.DOCUMENTS_REVISION.value,
}

CLIENT_DOCUMENT_VISIBLE_STATUSES = {
    ApplicationStatus.READY_FOR_CLIENT.value,
    ApplicationStatus.COMPLETED.value,
    ApplicationStatus.DISPUTE.value,
}


#: Расписку ИФНС клиент загружает, когда документы выданы и он подал их в
#: налоговую. Спор — нет: пока он открыт, неизвестно, будет ли регистрация.
IFNS_RECEIPT_STATUSES = {
    ApplicationStatus.READY_FOR_CLIENT.value,
    ApplicationStatus.COMPLETED.value,
}
#: Расписка — скан или фото: только такие форматы.
IFNS_RECEIPT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff"}
#: Дата регистрации из расписки: ИФНС регистрирует за несколько рабочих дней.
#: Дальше месяца вперёд — почти наверняка опечатка; раньше трёх месяцев назад —
#: тоже (такую расписку загружать уже незачем).
IFNS_DATE_MAX_AHEAD_DAYS = 30
IFNS_DATE_MAX_BEHIND_DAYS = 90
#: Расписка с персональными данными клиента собственнику не нужна.
OWNER_HIDDEN_KINDS = {DocumentFileKind.IFNS_RECEIPT.value}
#: «Сегодня» для дат из расписки — по Москве (сервер живёт в UTC).
_MOSCOW = timezone(timedelta(hours=3))


def application_document_download_url(application_id: UUID, file_id: UUID) -> str:
    return f"/workflow/applications/{application_id}/documents/{file_id}/download"


def application_document_read(file_record: StoredFile) -> ApplicationDocumentRead:
    if file_record.application_id is None:
        raise ValueError("Документ не привязан к заявке")
    return ApplicationDocumentRead(
        id=file_record.id,
        application_id=file_record.application_id,
        kind=DocumentFileKind(file_record.kind),
        original_filename=file_record.original_filename,
        content_type=file_record.content_type,
        size_bytes=file_record.size_bytes,
        created_at=file_record.created_at,
        uploaded_by=file_record.uploaded_by,
        download_url=application_document_download_url(file_record.application_id, file_record.id),
    )


def _role_for_user(user: User | object) -> UserRole:
    try:
        return UserRole(getattr(user, "role"))
    except ValueError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для документов заявки") from e


def _is_staff_role(role: UserRole) -> bool:
    return role in {UserRole.ADMIN, UserRole.MANAGER, UserRole.LAWYER}


def ensure_application_document_access(
    *,
    application: Application,
    user: User | object,
    for_download: bool = False,
) -> None:
    role = _role_for_user(user)
    if _is_staff_role(role):
        return
    if role == UserRole.OWNER:
        if getattr(user, "provider_id", None) is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя")
        if application.provider_id != getattr(user, "provider_id"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Заявка назначена другому исполнителю")
        return
    if role == UserRole.CLIENT:
        if application.created_by != getattr(user, "id", None):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Заявка принадлежит другому клиенту")
        if for_download and application.status not in CLIENT_DOCUMENT_VISIBLE_STATUSES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Документы еще не готовы к выдаче клиенту")
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав для документов заявки")


def ensure_owner_can_upload_document(application: Application, user: User | object, kind: DocumentFileKind) -> None:
    role = _role_for_user(user)
    if role != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Загружать документы может только исполнитель")
    ensure_application_document_access(application=application, user=user)
    if application.status not in OWNER_UPLOAD_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Исполнительские документы можно загружать только на этапе подготовки или доработки документов",
        )
    if kind not in OWNER_UPLOAD_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Этот тип документа недоступен исполнителю")


async def load_application_for_documents(db: AsyncSession, application_id: UUID) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")
    return application


async def upload_application_document(
    *,
    db: AsyncSession,
    application_id: UUID,
    file_content: bytes,
    original_filename: str,
    content_type: str,
    kind: DocumentFileKind,
    user: User | object,
) -> ApplicationDocumentUploadResult:
    application = await load_application_for_documents(db, application_id)
    ensure_owner_can_upload_document(application, user, kind)
    if not file_content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл пустой")

    previous_status = ApplicationStatus(application.status)
    file_record = await create_stored_file_record(
        db=db,
        content=file_content,
        kind=kind.value,
        original_filename=original_filename,
        content_type=content_type,
        application_id=application.id,
        uploaded_by=getattr(user, "id", None),
    )
    application.status = ApplicationStatus.DOCUMENTS_REVIEW.value
    # Мяч перешёл к оператору — срок теперь наш, а не собственника.
    apply_sla(application)

    document = application_document_read(file_record)
    payload = {
        "file_id": str(document.id),
        "kind": kind.value,
        "previous_status": previous_status.value,
        "status": ApplicationStatus.DOCUMENTS_REVIEW.value,
    }
    created_by = getattr(user, "id", None)
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.DOCUMENT_UPLOADED,
        audience=NotificationAudience.OWNER,
        title="Документ загружен",
        message=f"Файл {document.original_filename} отправлен на проверку площадки.",
        payload=payload,
        created_by=created_by,
    )
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.DOCUMENT_UPLOADED,
        audience=NotificationAudience.ADMIN,
        title="Исполнитель загрузил документы",
        message=f"Проверьте файл {document.original_filename} по заявке.",
        payload=payload,
        created_by=created_by,
    )
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.DOCUMENT_UPLOADED,
        audience=NotificationAudience.CLIENT,
        title="Документы переданы на проверку",
        message="Исполнитель загрузил комплект, площадка проверяет документы перед выдачей.",
        payload=payload,
        created_by=created_by,
    )
    await db.flush()
    return ApplicationDocumentUploadResult(
        application_id=application.id,
        application_status=ApplicationStatus.DOCUMENTS_REVIEW,
        document=document,
    )


async def list_application_documents(
    *,
    db: AsyncSession,
    application_id: UUID,
    user: User | object,
) -> list[ApplicationDocumentRead]:
    application = await load_application_for_documents(db, application_id)
    ensure_application_document_access(application=application, user=user, for_download=True)
    kinds = [kind.value for kind in DocumentFileKind]
    if _role_for_user(user) == UserRole.OWNER:
        kinds = [kind for kind in kinds if kind not in OWNER_HIDDEN_KINDS]
    result = await db.execute(
        select(StoredFile)
        .where(
            StoredFile.application_id == application.id,
            StoredFile.kind.in_(kinds),
        )
        .order_by(StoredFile.created_at.desc())
    )
    return [application_document_read(file_record) for file_record in result.scalars().all()]


async def get_application_document_moderation(
    *,
    db: AsyncSession,
    application_id: UUID,
    user: User | object,
) -> ApplicationDocumentModerationRead:
    application = await load_application_for_documents(db, application_id)
    role = workflow_role_for_user(user)
    if role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Модерация документов доступна только сотрудникам площадки")

    result = await db.execute(
        select(StoredFile)
        .where(
            StoredFile.application_id == application.id,
            StoredFile.kind.in_([kind.value for kind in DocumentFileKind]),
        )
        .order_by(StoredFile.created_at.desc())
    )
    documents = [application_document_read(file_record) for file_record in result.scalars().all()]

    return ApplicationDocumentModerationRead(
        application_id=application.id,
        status=ApplicationStatus(application.status),
        requires_manual_review=application.status == ApplicationStatus.DOCUMENTS_REVIEW.value,
        available_actions=next_actions_for_status(application.status, UserRole.ADMIN),
        documents=documents,
    )


async def get_application_document(
    *,
    db: AsyncSession,
    application_id: UUID,
    file_id: UUID,
    user: User | object,
) -> StoredFile:
    application = await load_application_for_documents(db, application_id)
    ensure_application_document_access(application=application, user=user, for_download=True)
    file_record = await db.get(StoredFile, file_id)
    if file_record is None or file_record.application_id != application.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ заявки не найден")
    try:
        DocumentFileKind(file_record.kind)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ заявки не найден") from e
    if file_record.kind in OWNER_HIDDEN_KINDS and _role_for_user(user) == UserRole.OWNER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ заявки не найден")
    return file_record


async def upload_ifns_receipt(
    *,
    db: AsyncSession,
    application_id: UUID,
    file_content: bytes,
    original_filename: str,
    expected_registration_on: date,
    user: User | object,
    now: datetime,
) -> tuple[Application, ApplicationDocumentRead]:
    """Клиент загружает расписку ИФНС и дату предстоящей регистрации из неё.

    Повторная загрузка (переподача после отказа, исправленная дата) разрешена:
    трекер берёт последнюю. После подтверждения регистрации — уже незачем.
    """
    application = await load_application_for_documents(db, application_id)
    if _role_for_user(user) != UserRole.CLIENT or application.created_by != getattr(user, "id", None):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")
    if application.status not in IFNS_RECEIPT_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Расписку загружают после получения документов и подачи их в ИФНС.",
        )
    if application.registration_confirmed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Регистрация уже подтверждена — расписка не нужна.")
    suffix = Path(original_filename or "").suffix.lower()
    if suffix not in IFNS_RECEIPT_EXTENSIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Расписку загрузите сканом или фото: PDF, JPG, PNG, WEBP, HEIC или TIFF.",
        )
    ensure_within_limits(content=file_content, original_filename=original_filename)
    today = now.astimezone(_MOSCOW).date()
    if expected_registration_on > today + timedelta(days=IFNS_DATE_MAX_AHEAD_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Дата регистрации слишком далеко — проверьте дату в расписке.",
        )
    if expected_registration_on < today - timedelta(days=IFNS_DATE_MAX_BEHIND_DAYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Дата регистрации слишком давняя — проверьте дату в расписке.",
        )

    file_record = await create_stored_file_record(
        db=db,
        content=file_content,
        kind=DocumentFileKind.IFNS_RECEIPT.value,
        original_filename=original_filename,
        content_type=content_type_for(original_filename),
        application_id=application.id,
        uploaded_by=getattr(user, "id", None),
    )
    application.registration_expected_on = expected_registration_on
    application.ifns_receipt_uploaded_at = now
    document = application_document_read(file_record)

    when = expected_registration_on.strftime("%d.%m.%Y")
    payload = {"file_id": str(document.id), "registration_expected_on": expected_registration_on.isoformat()}
    created_by = getattr(user, "id", None)
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.DOCUMENT_UPLOADED,
        audience=NotificationAudience.CLIENT,
        title="Расписка загружена",
        message=f"Регистрация ожидается {when}. После неё площадка сверит данные с ЕГРЮЛ.",
        payload=payload,
        created_by=created_by,
    )
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.DOCUMENT_UPLOADED,
        audience=NotificationAudience.ADMIN,
        title="Клиент подал документы в ИФНС",
        message=f"Загружена расписка, регистрация ожидается {when}. После этой даты сверьте регистрацию с ЕГРЮЛ.",
        payload=payload,
        created_by=created_by,
    )
    # Собственнику — без файла (в расписке персональные данные клиента), но с
    # датой: от регистрации зависит его выплата.
    await create_application_event(
        db=db,
        application_id=application.id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.OWNER,
        title="Клиент подал документы в ИФНС",
        message=f"Регистрация по вашему адресу ожидается {when}.",
        payload={"registration_expected_on": expected_registration_on.isoformat()},
        created_by=created_by,
    )
    await db.flush()
    return application, document
