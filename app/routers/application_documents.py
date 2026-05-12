from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.enums import DocumentFileKind
from app.models.user import User
from app.schemas.application_document import (
    ApplicationDocumentModerationRead,
    ApplicationDocumentRead,
    ApplicationDocumentUploadResult,
)
from app.services.application_documents import (
    get_application_document,
    get_application_document_moderation,
    list_application_documents,
    upload_application_document,
)
from app.services.storage import local_stored_file_path, read_stored_file_async

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
            headers={"Content-Disposition": f'attachment; filename="{file_record.original_filename}"'},
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
