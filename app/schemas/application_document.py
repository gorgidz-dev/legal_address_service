from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.enums import ApplicationStatus, DocumentFileKind


class ApplicationDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    kind: DocumentFileKind
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    uploaded_by: UUID | None
    download_url: str


class ApplicationDocumentUploadResult(BaseModel):
    application_id: UUID
    application_status: ApplicationStatus
    document: ApplicationDocumentRead


class IfnsReceiptDataRead(BaseModel):
    """Что найдено в PDF расписки ИФНС (app/services/ifns_receipt.py)."""
    has_text: bool = True
    looks_like_receipt: bool = False
    expected_on: Optional[date] = None
    submitted_on: Optional[date] = None
    company_name: Optional[str] = None
    inn: Optional[str] = None
    ogrn: Optional[str] = None
    number: Optional[str] = None
    form: Optional[str] = None
    ifns: Optional[str] = None


class IfnsReceiptUploadResult(BaseModel):
    """Ответ на загрузку расписки ИФНС: что теперь показывает трекер."""
    application_id: UUID
    registration_expected_on: date
    ifns_receipt_uploaded_at: datetime
    receipt: IfnsReceiptDataRead
    document: ApplicationDocumentRead


class ApplicationDocumentModerationRead(BaseModel):
    application_id: UUID
    status: ApplicationStatus
    requires_manual_review: bool
    available_actions: list[str]
    documents: list[ApplicationDocumentRead]
