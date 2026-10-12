from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, utcnow
from app.database import get_db
from app.enums import DocumentFileKind
from app.models.user import User
from app.schemas.application_document import (
    ApplicationDocumentModerationRead,
    ApplicationDocumentRead,
    ApplicationDocumentUploadResult,
    IfnsReceiptDataRead,
    IfnsReceiptUploadResult,
)
from app.services.application_documents import (
    get_application_document,
    get_application_document_moderation,
    list_application_documents,
    upload_application_document,
    preview_ifns_receipt,
    upload_ifns_receipt,
)
from app.services.storage import attachment_disposition, local_stored_file_path, read_stored_file_async

router = APIRouter(prefix="/workflow/applications", tags=["application-documents"])


@router.get("/{application_id}/documents", response_model=list[ApplicationDocumentRead])
async def list_documents(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApplicationDocumentRead]:
    return await list_application_documents(db=db, application_id=application_id, user=user)


@router.get("/{application_id}/moderation", response_model=ApplicationDocumentModerationRead)
async def document_moderation(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationDocumentModerationRead:
    return await get_application_document_moderation(db=db, application_id=application_id, user=user)


@router.post(
    "/{application_id}/documents",
    response_model=ApplicationDocumentUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    application_id: UUID,
    file: UploadFile = File(...),
    kind: DocumentFileKind = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationDocumentUploadResult:
    result = await upload_application_document(
        db=db,
        application_id=application_id,
        file_content=await file.read(),
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        kind=kind,
        user=user,
    )
    await db.commit()
    return result


@router.post("/{application_id}/ifns-receipt/preview", response_model=IfnsReceiptDataRead)
async def preview_receipt(
    application_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IfnsReceiptDataRead:
    """Клиент: что найдено в PDF расписки — до сохранения (проверить дату и название)."""
    receipt = await preview_ifns_receipt(
        db=db,
        application_id=application_id,
        file_content=await file.read(),
        original_filename=file.filename or "receipt",
        user=user,
    )
    return IfnsReceiptDataRead(**receipt.as_json())


@router.post(
    "/{application_id}/ifns-receipt",
    response_model=IfnsReceiptUploadResult,
    status_code=status.HTTP_201_CREATED,
)
async def upload_receipt(
    application_id: UUID,
    file: UploadFile = File(...),
    expected_registration_on: date = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IfnsReceiptUploadResult:
    """Клиент: расписка ИФНС о приёме документов + дата регистрации из неё."""
    application, document = await upload_ifns_receipt(
        db=db,
        application_id=application_id,
        file_content=await file.read(),
        original_filename=file.filename or "receipt",
        expected_registration_on=expected_registration_on,
        user=user,
        now=utcnow(),
    )
    await db.commit()
    return IfnsReceiptUploadResult(
        application_id=application.id,
        registration_expected_on=application.registration_expected_on,
        ifns_receipt_uploaded_at=application.ifns_receipt_uploaded_at,
        receipt=IfnsReceiptDataRead(**(application.ifns_receipt_data or {})),
        document=document,
    )


@router.get("/{application_id}/documents/{file_id}/download", response_model=None)
async def download_document(
    application_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    file_record = await get_application_document(
        db=db,
        application_id=application_id,
        file_id=file_id,
        user=user,
    )
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
