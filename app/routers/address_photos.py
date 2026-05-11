from __future__ import annotations

"""HTTP-маршруты для фотографий адреса.

- owner загружает / удаляет / переставляет фото своих адресов;
- админ модерирует (approve/reject) и видит всю очередь;
- публичный GET /address-photos/{id}/raw отдаёт байты:
    * approved -> открыт всем;
    * pending/rejected -> только владельцу или админу.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin
from app.database import AsyncSessionLocal, get_db
from app.enums import AddressPhotoModerationStatus, UserRole
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.address_photo import (
    AddressPhotoAdminRead,
    AddressPhotoRead,
    AddressPhotoRejectPayload,
    AddressPhotoReorderPayload,
)
from app.services.address_photos import (
    _ensure_address_owner_or_admin,
    approve_photo,
    delete_photo,
    list_address_photos,
    list_pending_photos,
    photo_to_admin_dict,
    reject_photo,
    set_main_photo,
    upload_address_photo,
)
from app.services.storage import LocalObjectStorage, S3ObjectStorage, get_object_storage


router = APIRouter(tags=["address-photos"])


# ------------------- owner / admin: загрузка и список -------------------

@router.post(
    "/owner/addresses/{address_id}/photos",
    response_model=AddressPhotoAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def owner_upload_photo(
    address_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AddressPhotoAdminRead:
    if user.role not in {UserRole.OWNER.value, UserRole.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль собственника или администратора")
    content = await file.read()
    photo = await upload_address_photo(
        db=db,
        address_id=address_id,
        file_content=content,
        original_filename=file.filename or "photo.jpg",
        content_type=file.content_type or "application/octet-stream",
        user=user,
    )
    await db.commit()
    return AddressPhotoAdminRead.model_validate(photo_to_admin_dict(photo))


@router.get(
    "/owner/addresses/{address_id}/photos",
    response_model=list[AddressPhotoAdminRead],
)
async def owner_list_photos(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AddressPhotoAdminRead]:
    if user.role not in {UserRole.OWNER.value, UserRole.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль собственника или администратора")
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    _ensure_address_owner_or_admin(user, address)
    photos = await list_address_photos(db=db, address_id=address_id, only_approved=False)
    return [AddressPhotoAdminRead.model_validate(photo_to_admin_dict(p)) for p in photos]


@router.delete("/owner/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def owner_delete_photo(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    if user.role not in {UserRole.OWNER.value, UserRole.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль собственника или администратора")
    await delete_photo(db=db, photo_id=photo_id, user=user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/owner/photos/{photo_id}/main",
    response_model=AddressPhotoAdminRead,
)
async def owner_set_main(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AddressPhotoAdminRead:
    if user.role not in {UserRole.OWNER.value, UserRole.ADMIN.value}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нужна роль собственника или администратора")
    photo = await set_main_photo(db=db, photo_id=photo_id, user=user)
    await db.commit()
    return AddressPhotoAdminRead.model_validate(photo_to_admin_dict(photo))


# ------------------- admin: модерация -------------------


@router.get(
    "/admin/address-photos/pending",
    response_model=list[AddressPhotoAdminRead],
)
async def admin_pending_queue(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[AddressPhotoAdminRead]:
    photos = await list_pending_photos(db=db)
    return [AddressPhotoAdminRead.model_validate(photo_to_admin_dict(p)) for p in photos]


@router.post(
    "/admin/address-photos/{photo_id}/approve",
    response_model=AddressPhotoAdminRead,
)
async def admin_approve(
    photo_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> AddressPhotoAdminRead:
    photo = await approve_photo(db=db, photo_id=photo_id, user=user)
    await db.commit()
    return AddressPhotoAdminRead.model_validate(photo_to_admin_dict(photo))


@router.post(
    "/admin/address-photos/{photo_id}/reject",
    response_model=AddressPhotoAdminRead,
)
async def admin_reject(
    photo_id: UUID,
    payload: AddressPhotoRejectPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> AddressPhotoAdminRead:
    photo = await reject_photo(db=db, photo_id=photo_id, user=user, comment=payload.comment)
    await db.commit()
    return AddressPhotoAdminRead.model_validate(photo_to_admin_dict(photo))


# ------------------- публичная отдача байтов -------------------


@router.get("/address-photos/{photo_id}/raw")
async def serve_photo_raw(
    photo_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Отдаёт байты картинки.

    Для approved-фото доступ публичный (без сессии). Для pending/rejected —
    только собственнику этого адреса или админу. Аутентификация здесь делается
    вручную, потому что роут зарегистрирован как public (см. _is_public_path).
    """
    photo = await db.get(AddressPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Фото не найдено")

    if photo.moderation_status != AddressPhotoModerationStatus.APPROVED.value:
        # Эта ветка отрабатывает только если middleware пустил запрос без сессии.
        # Для надёжности сами проверим, что есть валидный пользователь.
        user = await _resolve_user_from_request(request, db)
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Требуется вход для просмотра неодобренного фото",
            )
        address = await db.get(Address, photo.address_id)
        if address is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
        _ensure_address_owner_or_admin(user, address)

    return _serve_stored_photo(photo)


def _serve_stored_photo(photo: AddressPhoto) -> Response:
    storage = get_object_storage()
    if isinstance(storage, LocalObjectStorage):
        try:
            local_path = storage.path_for(photo.storage_key)
        except FileNotFoundError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Файл потерян на диске") from e
        return FileResponse(
            local_path,
            media_type=photo.content_type,
            filename=photo.original_filename,
        )
    if isinstance(storage, S3ObjectStorage):
        return Response(
            content=storage.read_bytes(photo.storage_key),
            media_type=photo.content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Неизвестный backend хранилища")


async def _resolve_user_from_request(
    request: Request, db: AsyncSession
) -> Optional[User]:
    """Возвращает текущего пользователя, если в запросе есть валидная сессия.

    Используется только для частичной защиты /address-photos/{id}/raw —
    публичный middleware пропускает запрос как анонимный, а тут уже мы сами
    решаем, давать ли pending/rejected.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        user = await db.get(User, user_id)
        if user is not None and user.is_active:
            return user

    from app.config import settings
    from app.services.auth_security import hash_token

    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        authorization = request.headers.get("authorization", "")
        scheme, _, candidate = authorization.partition(" ")
        if scheme.lower() == "bearer" and candidate.strip():
            token = candidate.strip()
    if not token:
        return None

    from sqlalchemy import select

    from app.auth import utcnow

    async with AsyncSessionLocal() as session_db:
        result = await session_db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
                User.is_active.is_(True),
            )
        )
        row = result.first()
    if row is None:
        return None
    _, user = row
    return user
