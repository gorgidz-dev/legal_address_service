from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_staff, utcnow
from app.database import get_db
from app.models.client import Client
from app.models.payment_document import PaymentDocument
from app.models.stored_file import StoredFile
from app.models.user import User
from app.schemas.client import (
    ClientRead,
    ClientUpdate,
    DaDataLookupResponse,
    PaymentDocumentRead,
)
from app.services.dadata import (
    DaDataError,
    DaDataNotConfigured,
    get_dadata_service,
)
from app.services.storage import (
    create_stored_file_record,
    local_stored_file_path,
    read_stored_file,
)
from app.validators import INNLegal

router = APIRouter(prefix="/clients", tags=["clients"], dependencies=[Depends(require_staff)])


@router.get(
    "/lookup-by-inn",
    response_model=DaDataLookupResponse,
    summary="Поиск ЮЛ в ЕГРЮЛ через DaData",
    description=(
        "Возвращает данные клиента по ИНН (10 знаков), включая блокеры — "
        "статус ликвидации, дисквалификация подписанта, признак филиала. "
        "Используется на форме создания заявки address_change.\n\n"
        "Кэш: повторные запросы с тем же ИНН в течение 24 часов "
        "не дёргают DaData."
    ),
    responses={
        404: {"description": "ИНН не найден в ЕГРЮЛ"},
        502: {"description": "DaData недоступна"},
        503: {"description": "DaData не настроена (DADATA_TOKEN отсутствует)"},
    },
)
async def lookup_by_inn(inn: INNLegal) -> DaDataLookupResponse:
    try:
        service = get_dadata_service()
    except DaDataNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    try:
        result = await service.lookup(inn)
    except DaDataError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    if result is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"ИНН {inn} не найден в ЕГРЮЛ",
        )
    return result


@router.get("/{client_id}", response_model=ClientRead)
async def get_client(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")
    return client


@router.patch(
    "/{client_id}",
    response_model=ClientRead,
    summary="Дозаполнить вручную те поля, которых нет в DaData (банк, e-mail и т.п.)",
)
async def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
) -> Client:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, key, value)
    await db.commit()
    await db.refresh(client)
    return client


def _payment_document_read(payment_document: PaymentDocument, file_record: StoredFile) -> PaymentDocumentRead:
    return PaymentDocumentRead(
        id=payment_document.id,
        client_id=payment_document.client_id,
        file_id=file_record.id,
        original_filename=file_record.original_filename,
        content_type=file_record.content_type,
        size_bytes=file_record.size_bytes,
        payment_date=payment_document.payment_date,
        amount=payment_document.amount,
        comment=payment_document.comment,
        created_at=payment_document.created_at,
        uploaded_by=payment_document.uploaded_by,
        download_url=f"/clients/{payment_document.client_id}/payment-documents/{payment_document.id}/download",
    )


@router.get(
    "/{client_id}/payment-documents",
    response_model=list[PaymentDocumentRead],
    summary="Документы об оплате по карточке клиента",
)
async def list_payment_documents(
    client_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PaymentDocumentRead]:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")

    result = await db.execute(
        select(PaymentDocument, StoredFile)
        .join(StoredFile, StoredFile.id == PaymentDocument.file_id)
        .where(PaymentDocument.client_id == client_id)
        .order_by(PaymentDocument.created_at.desc())
    )
    return [_payment_document_read(payment_document, file_record) for payment_document, file_record in result.all()]


@router.post(
    "/{client_id}/payment-documents",
    response_model=PaymentDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить документ об оплате в карточку клиента",
)
async def upload_payment_document(
    client_id: UUID,
    file: UploadFile = File(...),
    payment_date_: date | None = Form(None, alias="payment_date"),
    amount: Decimal | None = Form(None),
    comment: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PaymentDocumentRead:
    client = await db.get(Client, client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Client {client_id} не найден")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл пустой")

    file_record = await create_stored_file_record(
        db=db,
        content=content,
        kind="payment_document",
        original_filename=file.filename or "payment-document",
        content_type=file.content_type or "application/octet-stream",
        client_id=client_id,
        uploaded_by=user.id,
    )
    payment_document = PaymentDocument(
        client_id=client_id,
        file_id=file_record.id,
        payment_date=payment_date_,
        amount=amount,
        comment=comment,
        created_at=utcnow(),
        uploaded_by=user.id,
    )
    db.add(payment_document)
    await db.commit()
    await db.refresh(payment_document)
    await db.refresh(file_record)
    return _payment_document_read(payment_document, file_record)


@router.get(
    "/{client_id}/payment-documents/{document_id}/download",
    summary="Скачать документ об оплате",
    response_model=None,
)
async def download_payment_document(
    client_id: UUID,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    result = await db.execute(
        select(PaymentDocument, StoredFile)
        .join(StoredFile, StoredFile.id == PaymentDocument.file_id)
        .where(
            PaymentDocument.id == document_id,
            PaymentDocument.client_id == client_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ об оплате не найден")
    _, file_record = row

    try:
        local_path = local_stored_file_path(file_record)
        if local_path is not None:
            return FileResponse(
                local_path,
                filename=file_record.original_filename,
                media_type=file_record.content_type,
            )

        return Response(
            content=read_stored_file(file_record),
            media_type=file_record.content_type,
            headers={"Content-Disposition": f'attachment; filename="{file_record.original_filename}"'},
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
