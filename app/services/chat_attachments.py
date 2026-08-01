"""Вложения в переписке: что можно приложить, где это лежит, кто это скачает.

Тип файла определяем по расширению и им же подменяем присланный content-type.
Причина не в педантизме: файл отдаётся с нашего же домена, и «картинка», внутри
которой лежит HTML, выполнилась бы в контексте сессии пользователя. Расширение
проверяемо, заголовок от загрузчика — нет.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address_chat import AddressChat, AddressChatMessage, ChatMessageAttachment
from app.models.stored_file import StoredFile
from app.services.storage import create_stored_file_record

#: 15 МБ — скан договора на десяток страниц помещается, видео с телефона нет.
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024

#: Больше пяти файлов за раз — это уже архив, пусть присылают архивом.
MAX_ATTACHMENTS_PER_MESSAGE = 5

#: Расширение → тип, с которым файл будет отдаваться обратно. Список закрытый:
#: всё, чего здесь нет, отклоняем с понятным текстом, а не молча сохраняем.
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".rtf": "application/rtf",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    # Открепленная подпись рядом с подписанным документом.
    ".sig": "application/pkcs7-signature",
    ".p7s": "application/pkcs7-signature",
}

#: kind в stored_files. Отличает вложение переписки от документа заявки —
#: они лежат в одной таблице, и выборки по заявке не должны их смешивать.
CHAT_ATTACHMENT_KIND = "chat_attachment"

ALLOWED_HINT = "PDF, изображение, документ Word/Excel, текст, ZIP или подпись"


def content_type_for(original_filename: str) -> str:
    """Тип по расширению; неизвестное расширение — отказ."""
    suffix = Path(original_filename or "").suffix.lower()
    content_type = ALLOWED_EXTENSIONS.get(suffix)
    if content_type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Такой файл приложить нельзя. Подойдёт {ALLOWED_HINT}.",
        )
    return content_type


def ensure_within_limits(*, content: bytes, original_filename: str) -> None:
    if not content:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Файл {original_filename} пустой",
        )
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Файл больше {MAX_ATTACHMENT_BYTES // (1024 * 1024)} МБ",
        )


def ensure_message_has_content(*, body: str, attachment_count: int) -> None:
    """Сообщение — это текст, файл или и то и другое, но не пустота."""
    if not body.strip() and attachment_count == 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Нечего отправлять: напишите сообщение или приложите файл",
        )
    if attachment_count > MAX_ATTACHMENTS_PER_MESSAGE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"За раз можно приложить не больше {MAX_ATTACHMENTS_PER_MESSAGE} файлов",
        )


async def attach_file(
    *,
    db: AsyncSession,
    chat: AddressChat,
    message: AddressChatMessage,
    content: bytes,
    original_filename: str,
    user: object,
) -> tuple[ChatMessageAttachment, StoredFile]:
    ensure_within_limits(content=content, original_filename=original_filename)
    file_record = await create_stored_file_record(
        db=db,
        content=content,
        kind=CHAT_ATTACHMENT_KIND,
        original_filename=original_filename,
        content_type=content_type_for(original_filename),
        chat_id=chat.id,
        uploaded_by=getattr(user, "id", None),
    )
    attachment = ChatMessageAttachment(
        message_id=message.id,
        file_id=file_record.id,
        uploaded_by=getattr(user, "id", None),
    )
    db.add(attachment)
    await db.flush()
    return attachment, file_record


async def attachments_for_messages(
    db: AsyncSession, message_ids: list[UUID]
) -> dict[UUID, list[tuple[ChatMessageAttachment, StoredFile]]]:
    """Вложения пачкой на всю страницу истории — иначе N+1 на каждое сообщение."""
    if not message_ids:
        return {}
    rows = (
        await db.execute(
            select(ChatMessageAttachment, StoredFile)
            .join(StoredFile, StoredFile.id == ChatMessageAttachment.file_id)
            .where(ChatMessageAttachment.message_id.in_(message_ids))
            .order_by(ChatMessageAttachment.created_at)
        )
    ).all()
    grouped: dict[UUID, list[tuple[ChatMessageAttachment, StoredFile]]] = {}
    for attachment, file_record in rows:
        grouped.setdefault(attachment.message_id, []).append((attachment, file_record))
    return grouped


async def load_attachment(
    *, db: AsyncSession, chat_id: UUID, attachment_id: UUID
) -> StoredFile:
    """Файл вложения — только если оно из этой ветки.

    Проверка «вложение принадлежит чату» здесь, а не в роутере: без неё участник
    одной переписки скачивал бы вложения любой другой по угаданному id.
    """
    row = (
        await db.execute(
            select(ChatMessageAttachment, StoredFile, AddressChatMessage)
            .join(StoredFile, StoredFile.id == ChatMessageAttachment.file_id)
            .join(
                AddressChatMessage,
                AddressChatMessage.id == ChatMessageAttachment.message_id,
            )
            .where(ChatMessageAttachment.id == attachment_id)
        )
    ).first()
    if row is None or row[2].chat_id != chat_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вложение не найдено")
    return row[1]


def attachment_download_url(chat_id: UUID, attachment_id: UUID) -> str:
    return f"/chats/{chat_id}/attachments/{attachment_id}/download"
