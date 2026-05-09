from __future__ import annotations

from datetime import datetime
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
