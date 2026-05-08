from __future__ import annotations

import hashlib
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.address import Address
from app.models.egrn_extract import EgrnExtract
from app.schemas.egrn import EgrnExtractRead
from app.services.storage import create_stored_file_record, egrn_storage_dir, relative_storage_url

router = APIRouter(tags=["egrn"])


@router.get(
    "/addresses/{address_id}/egrn-extracts",
    response_model=list[EgrnExtractRead],
    summary="История выписок ЕГРН по адресу",
)
async def list_extracts(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[EgrnExtract]:
    result = await db.execute(
        select(EgrnExtract)
        .where(EgrnExtract.address_id == address_id)
        .order_by(EgrnExtract.issue_date.desc(), EgrnExtract.uploaded_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/addresses/{address_id}/egrn-extracts",
    response_model=EgrnExtractRead,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить новую выписку (immutable PDF + опц. .sig)",
    description=(
        "Многочастная загрузка. Старая текущая выписка автоматически "
        "перестаёт быть актуальной (`is_current=false`), новая становится текущей. "
        "Старые версии остаются в БД для аудита."
    ),
)
async def upload_extract(
    address_id: UUID,
    pdf_file: UploadFile = File(..., description="PDF выписки от Росреестра"),
    issue_date_: date = Form(..., alias="issue_date", description="Дата формирования выписки"),
    extract_number: str | None = Form(None),
    signature_file: UploadFile | None = File(None, description="Открепленная ЭЦП .sig (если отдельный файл)"),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> EgrnExtract:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Address {address_id} не найден")

    pdf_bytes = await pdf_file.read()
    if not pdf_bytes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "PDF-файл пустой")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    target_dir = egrn_storage_dir(address_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{pdf_sha256}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    await create_stored_file_record(
        db=db,
        content=pdf_bytes,
        kind="egrn_pdf",
        original_filename=pdf_file.filename or f"{pdf_sha256}.pdf",
        content_type=pdf_file.content_type or "application/pdf",
    )

    signature_url = None
    if signature_file is not None:
        signature_bytes = await signature_file.read()
        if signature_bytes:
            suffix = ".sig"
            if signature_file.filename and "." in signature_file.filename:
                suffix = "." + signature_file.filename.rsplit(".", 1)[1]
            signature_path = target_dir / f"{pdf_sha256}{suffix}"
            signature_path.write_bytes(signature_bytes)
            signature_url = relative_storage_url(signature_path)
            await create_stored_file_record(
                db=db,
                content=signature_bytes,
                kind="egrn_signature",
                original_filename=signature_file.filename or f"{pdf_sha256}{suffix}",
                content_type=signature_file.content_type or "application/octet-stream",
            )

    current_result = await db.execute(
        select(EgrnExtract).where(
            EgrnExtract.address_id == address_id,
            EgrnExtract.is_current.is_(True),
        )
    )
    for old_extract in current_result.scalars().all():
        old_extract.is_current = False

    extract = EgrnExtract(
        address_id=address_id,
        pdf_file_url=relative_storage_url(pdf_path),
        signature_file_url=signature_url,
        extract_number=extract_number,
        issue_date=issue_date_,
        expires_at=issue_date_.fromordinal(
            issue_date_.toordinal() + settings.egrn_extract_validity_days
        ),
        pdf_sha256=pdf_sha256,
        is_current=True,
        notes=notes,
    )
    db.add(extract)
    await db.commit()
    await db.refresh(extract)
    return extract


@router.get(
    "/egrn-extracts/{extract_id}",
    response_model=EgrnExtractRead,
)
async def get_extract(
    extract_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> EgrnExtract:
    extract = await db.get(EgrnExtract, extract_id)
    if extract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"EGRN extract {extract_id} не найден")
    return extract
