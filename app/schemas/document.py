from __future__ import annotations

"""Схемы для договоров, гарантийных писем, шаблонов и сгенерированных документов."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enums import GeneratedDocumentKind, GuaranteeVariant, TemplateKind


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    number: str = Field(examples=["ДА-2026-0042"])
    contract_date: date
    start_date: date
    end_date: date
    price_total: Decimal
    price_total_in_words: str
    created_at: datetime


class GuaranteeLetterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    variant: GuaranteeVariant
    number: str = Field(examples=["ГП-2026-0042"])
    letter_date: date
    egrn_extract_id: UUID
    created_at: datetime


# ============================================================
# Шаблоны .docx — версионирование
# ============================================================

class DocumentTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: TemplateKind
    version: int
    file_url: str
    file_sha256: str
    is_active: bool
    comment: Optional[str]
    uploaded_at: datetime
    uploaded_by: Optional[UUID]


class DocumentTemplateUploadResult(BaseModel):
    """Результат загрузки новой версии шаблона: тестовая генерация + статус."""

    template: DocumentTemplateRead
    test_render_succeeded: bool
    test_render_error: Optional[str] = None
    test_render_pdf_url: Optional[str] = None


# ============================================================
# Сгенерированные документы — журнал по заявке
# ============================================================

class GeneratedDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    kind: GeneratedDocumentKind
    template_id: Optional[UUID]
    egrn_extract_id: Optional[UUID]
    docx_url: Optional[str]
    pdf_url: Optional[str]
    zip_url: Optional[str]
    generated_at: datetime
    generated_by: Optional[UUID]


class PackageGenerateResult(BaseModel):
    """Результат сборки полного комплекта документов по заявке."""

    application_id: UUID
    zip_url: str
    documents: list[GeneratedDocumentRead]
