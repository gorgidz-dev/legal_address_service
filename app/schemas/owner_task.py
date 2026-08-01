"""Поручение собственнику."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums import OwnerTaskStatus


class OwnerTaskRead(BaseModel):
    id: UUID
    provider_id: UUID
    address_id: Optional[UUID] = None
    #: Адрес строкой — иначе кабинету пришлось бы искать его по своему списку.
    address_label: Optional[str] = None

    title: str
    description: Optional[str] = None
    status: OwnerTaskStatus
    due_on: Optional[date] = None
    #: Отрицательное — срок вышел. None, если срока нет или задача закрыта.
    days_until_due: Optional[int] = None

    created_at: datetime
    completed_at: Optional[datetime] = None


class OwnerTaskCreate(BaseModel):
    provider_id: UUID
    address_id: Optional[UUID] = None
    title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    due_on: Optional[date] = None


class OwnerTaskTemplate(BaseModel):
    title: str
    description: str
