"""Правоустанавливающие документы адреса: доступ, загрузка, удаление.

Проверка прав здесь одна на все операции: документ принадлежит адресу, адрес —
организации собственника. Разнеси её по роутеру — и однажды новая ручка
появится без проверки.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AddressDocumentKind, UserRole
from app.models.address import Address
from app.models.address_document import AddressDocument
from app.models.stored_file import StoredFile
from app.services.storage import create_stored_file_record

#: Сколько дней вперёд документ считается «скоро истекает». Совпадает с первой
#: вехой напоминаний, чтобы плашка в кабинете и письмо появлялись вместе.
EXPIRING_SOON_DAYS = 30


async def load_owner_address(
    *, db: AsyncSession, address_id: UUID, user: object
) -> Address:
    """Адрес, принадлежащий организации этого собственника, иначе 403/404."""
    if UserRole(getattr(user, "role")) != UserRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только собственнику")
    provider_id = getattr(user, "provider_id", None)
    if provider_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя"
        )
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    if address.provider_id != provider_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Адрес не принадлежит вашей организации"
        )
    return address


async def list_address_documents(
    *, db: AsyncSession, address_id: UUID
) -> list[tuple[AddressDocument, StoredFile]]:
    result = await db.execute(
        select(AddressDocument, StoredFile)
        .join(StoredFile, StoredFile.id == AddressDocument.file_id)
        .where(AddressDocument.address_id == address_id)
        # Сначала то, у чего срок ближе; бессрочные — в конец.
        .order_by(AddressDocument.expires_at.asc().nullslast(), AddressDocument.created_at.desc())
    )
    return list(result.all())


async def add_address_document(
    *,
    db: AsyncSession,
    address: Address,
    kind: AddressDocumentKind,
    title: str,
    content: bytes,
    original_filename: str,
    content_type: str,
    issued_on: date | None,
    expires_at: date | None,
    notes: str | None,
    user: object,
) -> tuple[AddressDocument, StoredFile]:
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл пустой")
    if issued_on and expires_at and expires_at < issued_on:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Срок действия не может быть раньше даты выдачи",
        )

    file_record = await create_stored_file_record(
        db=db,
        content=content,
        kind=f"address_{kind.value}",
        original_filename=original_filename,
        content_type=content_type,
        uploaded_by=getattr(user, "id", None),
    )
    document = AddressDocument(
        address_id=address.id,
        file_id=file_record.id,
        kind=kind.value,
        title=title.strip() or original_filename,
        issued_on=issued_on,
        expires_at=expires_at,
        notes=(notes or "").strip() or None,
        uploaded_by=getattr(user, "id", None),
        created_at=datetime.now(timezone.utc),
    )
    db.add(document)
    await db.flush()
    return document, file_record


async def delete_address_document(
    *, db: AsyncSession, address: Address, document_id: UUID
) -> None:
    document = await db.get(AddressDocument, document_id)
    if document is None or document.address_id != address.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден у этого адреса")
    # Сам файл в хранилище остаётся: на него может ссылаться выданный клиенту
    # комплект, а тихо удалить чужую ссылку хуже, чем оставить лишний файл.
    await db.delete(document)


def expiry_state(expires_at: date | None, *, today: date) -> str:
    """`none` — бессрочный, `expired`, `soon` или `valid`."""
    if expires_at is None:
        return "none"
    days = (expires_at - today).days
    if days < 0:
        return "expired"
    if days <= EXPIRING_SOON_DAYS:
        return "soon"
    return "valid"
