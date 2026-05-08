from __future__ import annotations

"""Pydantic-схемы для выписок ЕГРН (immutable PDF + опц. .sig)."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EgrnExtractMetadata(BaseModel):
    """Метаданные при загрузке. Файлы передаются отдельно multipart-ом."""

    extract_number: Optional[str] = Field(
        default=None, examples=["КУВИ-001/2026-12345"]
    )
    issue_date: date = Field(description="Дата формирования выписки Росреестром")
    notes: Optional[str] = None


class EgrnExtractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID

    extract_number: Optional[str]
    issue_date: date
    expires_at: date

    pdf_file_url: str
    signature_file_url: Optional[str]
    pdf_sha256: str

    is_current: bool
    replaced_by_id: Optional[UUID]

    uploaded_at: datetime
    uploaded_by: Optional[UUID]
    notes: Optional[str]
