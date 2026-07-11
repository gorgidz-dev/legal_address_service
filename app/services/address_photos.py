from __future__ import annotations

"""Бизнес-логика фотографий адреса.

Owner загружает фото своего адреса -> Pillow ресайзит до 1600x1200 max,
конвертирует в JPEG q=85 -> сохраняем через LocalObjectStorage.
Админ модерирует. Только одно главное фото на адрес (partial unique index).
"""

import asyncio
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.enums import AddressPhotoModerationStatus, UserRole
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.user import User
from app.services.storage import get_object_storage, safe_storage_filename


MAX_PHOTOS_PER_ADDRESS = 10
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MiB
MAX_DIMENSION = 1600  # длинная сторона после ресайза
JPEG_QUALITY = 85
ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp"}
)
OUTPUT_CONTENT_TYPE = "image/jpeg"
OUTPUT_EXTENSION = ".jpg"


@dataclass(frozen=True)
class ProcessedImage:
    content: bytes
    width: int
    height: int


def _ensure_address_owner_or_admin(user: User, address: Address) -> None:
    if user.role == UserRole.ADMIN.value:
        return
    if user.role == UserRole.OWNER.value and user.provider_id == address.provider_id:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Нет доступа к фотографиям этого адреса",
    )


async def _load_address(db: AsyncSession, address_id: UUID) -> Address:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    return address


async def _load_photo(db: AsyncSession, photo_id: UUID) -> AddressPhoto:
    photo = await db.get(AddressPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Фото не найдено")
    return photo


def process_image_bytes(content: bytes) -> ProcessedImage:
    """Приводит произвольное изображение к нормализованному JPEG.

    - валидирует, что это вообще картинка;
    - применяет EXIF-ориентацию (иначе фото с телефона будет повёрнуто);
    - конвертирует прозрачность на белый фон (JPEG не умеет alpha);
    - ужимает до MAX_DIMENSION по длинной стороне (без апскейла);
    - сохраняет JPEG q=85.
    """
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode in {"RGBA", "LA", "P"}:
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            return ProcessedImage(
                content=buffer.getvalue(),
                width=img.width,
                height=img.height,
            )
    except UnidentifiedImageError as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Не удалось распознать файл как изображение",
        ) from e
    except (OSError, ValueError) as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Файл повреждён или не поддерживается: {e}",
        ) from e


async def _count_photos(db: AsyncSession, address_id: UUID) -> int:
    result = await db.execute(
        select(func.count(AddressPhoto.id)).where(AddressPhoto.address_id == address_id)
    )
    return int(result.scalar_one() or 0)


async def upload_address_photo(
    *,
    db: AsyncSession,
    address_id: UUID,
    file_content: bytes,
    original_filename: str,
    content_type: str,
    user: User,
) -> AddressPhoto:
    address = await _load_address(db, address_id)
    _ensure_address_owner_or_admin(user, address)

    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Допустимые форматы: JPEG, PNG, WebP. Получено: {content_type}",
        )
    if len(file_content) == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустой файл")
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Файл больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
        )

    existing_count = await _count_photos(db, address_id)
    if existing_count >= MAX_PHOTOS_PER_ADDRESS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"У адреса уже {MAX_PHOTOS_PER_ADDRESS} фотографий — удалите ненужные перед загрузкой новой",
        )

    processed = await asyncio.to_thread(process_image_bytes, file_content)
    content_hash = hashlib.sha256(processed.content).hexdigest()
    safe_name = safe_storage_filename(original_filename or "photo.jpg")
    if not safe_name.lower().endswith(OUTPUT_EXTENSION):
        safe_name = f"{safe_name}{OUTPUT_EXTENSION}"
    key = f"addresses/{address_id}/photos/{content_hash[:16]}/{safe_name}"

    stored = await asyncio.to_thread(
        get_object_storage().put_bytes,
        key=key,
        content=processed.content,
        content_type=OUTPUT_CONTENT_TYPE,
    )

    photo = AddressPhoto(
        address_id=address_id,
        storage_backend=stored.backend,
        storage_key=stored.key,
        original_filename=original_filename or safe_name,
        content_type=OUTPUT_CONTENT_TYPE,
        size_bytes=len(processed.content),
        width=processed.width,
        height=processed.height,
        sha256=content_hash,
        moderation_status=AddressPhotoModerationStatus.PENDING.value,
        is_main=False,
        sort_order=existing_count,
        uploaded_by=user.id,
    )
    db.add(photo)
    await db.flush()
    await db.refresh(photo)
    return photo


async def list_address_photos(
    *,
    db: AsyncSession,
    address_id: UUID,
    only_approved: bool,
) -> list[AddressPhoto]:
    stmt = (
        select(AddressPhoto)
        .where(AddressPhoto.address_id == address_id)
        .order_by(AddressPhoto.is_main.desc(), AddressPhoto.sort_order, AddressPhoto.created_at)
    )
    if only_approved:
        stmt = stmt.where(
            AddressPhoto.moderation_status == AddressPhotoModerationStatus.APPROVED.value
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_pending_photos(*, db: AsyncSession) -> list[AddressPhoto]:
    """Очередь модерации для админа."""
    stmt = (
        select(AddressPhoto)
        .where(
            AddressPhoto.moderation_status == AddressPhotoModerationStatus.PENDING.value
        )
        .order_by(AddressPhoto.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль администратора")


async def approve_photo(
    *,
    db: AsyncSession,
    photo_id: UUID,
    user: User,
) -> AddressPhoto:
    _require_admin(user)
    photo = await _load_photo(db, photo_id)
    photo.moderation_status = AddressPhotoModerationStatus.APPROVED.value
    photo.moderation_comment = None
    photo.moderated_by = user.id
    photo.moderated_at = utcnow()
    await db.flush()
    await db.refresh(photo)
    return photo


async def reject_photo(
    *,
    db: AsyncSession,
    photo_id: UUID,
    user: User,
    comment: str,
) -> AddressPhoto:
    _require_admin(user)
    photo = await _load_photo(db, photo_id)
    photo.moderation_status = AddressPhotoModerationStatus.REJECTED.value
    photo.moderation_comment = comment
    photo.moderated_by = user.id
    photo.moderated_at = utcnow()
    # Отказанное фото не может оставаться главным.
    photo.is_main = False
    await db.flush()
    await db.refresh(photo)
    return photo


async def set_main_photo(
    *,
    db: AsyncSession,
    photo_id: UUID,
    user: User,
) -> AddressPhoto:
    photo = await _load_photo(db, photo_id)
    address = await _load_address(db, photo.address_id)
    _ensure_address_owner_or_admin(user, address)
    if photo.moderation_status != AddressPhotoModerationStatus.APPROVED.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Главным можно сделать только одобренное фото",
        )
    # Снимаем флаг с прочих фото этого адреса (partial unique index не даст иначе).
    await db.execute(
        update(AddressPhoto)
        .where(
            AddressPhoto.address_id == photo.address_id,
            AddressPhoto.id != photo.id,
            AddressPhoto.is_main.is_(True),
        )
        .values(is_main=False)
    )
    photo.is_main = True
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Не удалось установить фото как главное — конфликт уникальности",
        ) from e
    await db.refresh(photo)
    return photo


async def delete_photo(
    *,
    db: AsyncSession,
    photo_id: UUID,
    user: User,
) -> None:
    photo = await _load_photo(db, photo_id)
    address = await _load_address(db, photo.address_id)
    _ensure_address_owner_or_admin(user, address)
    await db.delete(photo)
    await db.flush()


def photo_public_url(photo: AddressPhoto) -> str:
    """URL для скачивания/отображения фото через FastAPI.

    Один маршрут на всех (admin/owner/public). Серверная сторона решает доступ
    по статусу модерации. Префикс /api/v1 — потому что роутер примонтирован
    в api_v1 (см. app/main.py), а middleware `_is_public_path` пропускает
    approved-фото только под этим префиксом.
    """
    return f"/api/v1/address-photos/{photo.id}/raw"


def photo_to_admin_dict(photo: AddressPhoto) -> dict:
    return {
        "id": photo.id,
        "address_id": photo.address_id,
        "url": photo_public_url(photo),
        "original_filename": photo.original_filename,
        "content_type": photo.content_type,
        "size_bytes": photo.size_bytes,
        "width": photo.width,
        "height": photo.height,
        "moderation_status": photo.moderation_status,
        "moderation_comment": photo.moderation_comment,
        "moderated_by": photo.moderated_by,
        "moderated_at": photo.moderated_at,
        "is_main": photo.is_main,
        "sort_order": photo.sort_order,
        "uploaded_by": photo.uploaded_by,
        "created_at": photo.created_at,
        "updated_at": photo.updated_at,
    }


def photo_to_public_dict(photo: AddressPhoto) -> dict:
    return {
        "id": photo.id,
        "address_id": photo.address_id,
        "url": photo_public_url(photo),
        "content_type": photo.content_type,
        "width": photo.width,
        "height": photo.height,
        "is_main": photo.is_main,
        "sort_order": photo.sort_order,
    }
