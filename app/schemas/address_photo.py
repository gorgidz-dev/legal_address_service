from __future__ import annotations

"""Pydantic-схемы фотографий адреса."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import AddressPhotoModerationStatus


class AddressPhotoRead(BaseModel):
    """Публичная карточка фото — только одобренные, минимум полей."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    url: str
    content_type: str
    width: int
    height: int
    is_main: bool
    sort_order: int


class AddressPhotoAdminRead(BaseModel):
    """Полная карточка фото для собственника/админа: статус, комментарий, авторы."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    url: str
    original_filename: str
    content_type: str
    size_bytes: int
    width: int
    height: int
    moderation_status: AddressPhotoModerationStatus
    moderation_comment: Optional[str]
    moderated_by: Optional[UUID]
    moderated_at: Optional[datetime]
    is_main: bool
    sort_order: int
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime


class AddressPhotoRejectPayload(BaseModel):
    comment: str = Field(min_length=2, max_length=500)


class AddressPhotoReorderPayload(BaseModel):
    photo_ids: list[UUID] = Field(min_length=1, max_length=20)
