"""Правоустанавливающие документы адреса — кабинет собственника.

Отдельный роутер, а не ручки в owner_dashboard: тот отдаёт сводку одним GET,
а здесь загрузка файла, скачивание и удаление.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.enums import ADDRESS_DOCUMENT_LABELS, AddressDocumentKind
from app.models.address_document import AddressDocument
from app.models.stored_file import StoredFile
from app.models.user import User
from app.schemas.address_document import AddressDocumentRead
from app.services.address_documents import (
    add_address_document,
    delete_address_document,
    expiry_state,
    list_address_documents,
    load_owner_address,
)
from app.services.storage import local_stored_file_path, read_stored_file_async

router = APIRouter(prefix="/owner/addresses", tags=["address-documents"])


def _download_url(address_id: UUID, document_id: UUID) -> str:
    return f"/owner/addresses/{address_id}/documents/{document_id}/download"


def _read(document: AddressDocument, file_record: StoredFile, *, today: date) -> AddressDocumentRead:
    state = expiry_state(document.expires_at, today=today)
    return AddressDocumentRead(
        id=document.id,
        address_id=document.address_id,
        kind=AddressDocumentKind(document.kind),
        kind_label=ADDRESS_DOCUMENT_LABELS.get(document.kind, "Документ"),
        title=document.title,
        original_filename=file_record.original_filename,
        size_bytes=file_record.size_bytes,
        download_url=_download_url(document.address_id, document.id),
        issued_on=document.issued_on,
        expires_at=document.expires_at,
        expiry_state=state,
        days_until_expiry=(
            (document.expires_at - today).days if document.expires_at else None
        ),
        notes=document.notes,
        created_at=document.created_at,
    )


@router.get(
    "/{address_id}/documents",
    response_model=list[AddressDocumentRead],
    summary="Документы по адресу",
)
async def list_documents(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AddressDocumentRead]:
    await load_owner_address(db=db, address_id=address_id, user=user)
    today = date.today()
    rows = await list_address_documents(db=db, address_id=address_id)
    return [_read(document, file_record, today=today) for document, file_record in rows]


@router.post(
    "/{address_id}/documents",
    response_model=AddressDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить документ по адресу",
)
async def upload_document(
    address_id: UUID,
    file: UploadFile = File(...),
    kind: AddressDocumentKind = Form(...),
    title: str = Form(""),
    issued_on: date | None = Form(None),
    expires_at: date | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AddressDocumentRead:
    address = await load_owner_address(db=db, address_id=address_id, user=user)
    content = await file.read()
    document, file_record = await add_address_document(
        db=db,
        address=address,
        kind=kind,
        title=title,
        content=content,
        original_filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
        issued_on=issued_on,
        expires_at=expires_at,
        notes=notes,
        user=user,
    )
    await db.commit()
    return _read(document, file_record, today=date.today())


@router.delete(
    "/{address_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить карточку документа",
)
async def remove_document(
    address_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    address = await load_owner_address(db=db, address_id=address_id, user=user)
    await delete_address_document(db=db, address=address, document_id=document_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{address_id}/documents/{document_id}/download",
    response_class=FileResponse,
    summary="Скачать документ",
)
async def download_document(
    address_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    await load_owner_address(db=db, address_id=address_id, user=user)
    document = await db.get(AddressDocument, document_id)
    if document is None or document.address_id != address_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден у этого адреса")
    file_record = await db.get(StoredFile, document.file_id)
    if file_record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл документа недоступен")

    path = local_stored_file_path(file_record)
    if path is not None:
        return FileResponse(
            path,
            filename=file_record.original_filename,
            media_type=file_record.content_type,
        )
    content = await read_stored_file_async(file_record)
    return Response(
        content=content,
        media_type=file_record.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_record.original_filename}"'
        },
    )
