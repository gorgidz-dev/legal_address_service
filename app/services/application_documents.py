from __future__ import annotations

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
from app.services.notification_events import create_application_event
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
    result = await db.execute(
        select(StoredFile)
        .where(
            StoredFile.application_id == application.id,
            StoredFile.kind.in_([kind.value for kind in DocumentFileKind]),
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
    return file_record
