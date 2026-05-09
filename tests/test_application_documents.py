from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.enums import (
    ApplicationEventKind,
    ApplicationStatus,
    ApplicationType,
    DocumentFileKind,
    NotificationAudience,
    UserRole,
)
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.stored_file import StoredFile
from app.schemas.application_document import ApplicationDocumentUploadResult
from app.services.application_documents import upload_application_document


def make_application(
    *,
    status: ApplicationStatus,
    provider_id: UUID | None = None,
    created_by: UUID | None = None,
) -> Application:
    now = datetime.now(timezone.utc)
    return Application(
        id=uuid4(),
        type=ApplicationType.ADDRESS_CHANGE.value,
        provider_id=provider_id or uuid4(),
        address_id=uuid4(),
        client_id=uuid4(),
        company_name="Дельта Кабинет",
        contact_name="Марина Орлова",
        contact_phone="+7 916 402-18-31",
        contact_email="client@example.ru",
        term_months=11,
        notice_period="1m",
        has_correspondence_service=False,
        status=status.value,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


class FakeDocumentSession:
    def __init__(self, application: Application):
        self.application = application
        self.added: list[object] = []
        self.flushed = False

    async def get(self, model, object_id):
        if model.__name__ == "Application" and object_id == self.application.id:
            return self.application
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed = True
        now = datetime.now(timezone.utc)
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()
            if getattr(item, "created_at", None) is None:
                item.created_at = now


async def fake_create_stored_file_record(
    *,
    db,
    content: bytes,
    kind: str,
    original_filename: str,
    content_type: str,
    client_id=None,
    application_id=None,
    uploaded_by=None,
) -> StoredFile:
    file_record = StoredFile(
        id=uuid4(),
        client_id=client_id,
        application_id=application_id,
        kind=kind,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256="a" * 64,
        storage_backend="local",
        storage_key=f"applications/{application_id}/{kind}/{original_filename}",
        public_url=None,
        created_at=datetime.now(timezone.utc),
        uploaded_by=uploaded_by,
    )
    db.add(file_record)
    return file_record


@pytest.mark.asyncio
async def test_owner_uploads_document_and_sends_application_to_review(monkeypatch) -> None:
    provider_id = uuid4()
    application = make_application(status=ApplicationStatus.DOCUMENTS_PREPARING, provider_id=provider_id)
    db = FakeDocumentSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)
    monkeypatch.setattr(
        "app.services.application_documents.create_stored_file_record",
        fake_create_stored_file_record,
    )

    result = await upload_application_document(
        db=db,
        application_id=application.id,
        file_content=b"%PDF signed consent",
        original_filename="consent.pdf",
        content_type="application/pdf",
        kind=DocumentFileKind.OWNER_CONSENT,
        user=owner,
    )

    assert isinstance(result, ApplicationDocumentUploadResult)
    assert application.status == ApplicationStatus.DOCUMENTS_REVIEW.value
    assert result.application_status == ApplicationStatus.DOCUMENTS_REVIEW
    assert result.document.kind == DocumentFileKind.OWNER_CONSENT
    assert result.document.download_url == f"/workflow/applications/{application.id}/documents/{result.document.id}/download"

    stored_file = next(item for item in db.added if isinstance(item, StoredFile))
    assert stored_file.application_id == application.id
    assert stored_file.uploaded_by == owner.id

    events = [item for item in db.added if isinstance(item, ApplicationEvent)]
    assert {event.audience for event in events} == {
        NotificationAudience.ADMIN.value,
        NotificationAudience.CLIENT.value,
        NotificationAudience.OWNER.value,
    }
    admin_event = next(event for event in events if event.audience == NotificationAudience.ADMIN.value)
    assert admin_event.kind == ApplicationEventKind.DOCUMENT_UPLOADED.value
    assert admin_event.payload == {
        "file_id": str(result.document.id),
        "kind": DocumentFileKind.OWNER_CONSENT.value,
        "previous_status": ApplicationStatus.DOCUMENTS_PREPARING.value,
        "status": ApplicationStatus.DOCUMENTS_REVIEW.value,
    }


@pytest.mark.asyncio
async def test_document_upload_rejects_empty_file(monkeypatch) -> None:
    provider_id = uuid4()
    application = make_application(status=ApplicationStatus.DOCUMENTS_PREPARING, provider_id=provider_id)
    db = FakeDocumentSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)
    monkeypatch.setattr(
        "app.services.application_documents.create_stored_file_record",
        fake_create_stored_file_record,
    )

    with pytest.raises(HTTPException) as exc:
        await upload_application_document(
            db=db,
            application_id=application.id,
            file_content=b"",
            original_filename="empty.pdf",
            content_type="application/pdf",
            kind=DocumentFileKind.OWNER_CONSENT,
            user=owner,
        )

    assert exc.value.status_code == 422
    assert application.status == ApplicationStatus.DOCUMENTS_PREPARING.value
    assert db.added == []


@pytest.mark.asyncio
async def test_document_upload_rejects_another_provider_application(monkeypatch) -> None:
    application = make_application(status=ApplicationStatus.DOCUMENTS_PREPARING, provider_id=uuid4())
    db = FakeDocumentSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=uuid4())
    monkeypatch.setattr(
        "app.services.application_documents.create_stored_file_record",
        fake_create_stored_file_record,
    )

    with pytest.raises(HTTPException) as exc:
        await upload_application_document(
            db=db,
            application_id=application.id,
            file_content=b"%PDF",
            original_filename="consent.pdf",
            content_type="application/pdf",
            kind=DocumentFileKind.OWNER_CONSENT,
            user=owner,
        )

    assert exc.value.status_code == 403
    assert application.status == ApplicationStatus.DOCUMENTS_PREPARING.value
    assert db.added == []


@pytest.mark.asyncio
async def test_document_upload_rejects_wrong_status(monkeypatch) -> None:
    provider_id = uuid4()
    application = make_application(status=ApplicationStatus.ACCEPTED_BY_OWNER, provider_id=provider_id)
    db = FakeDocumentSession(application)
    owner = SimpleNamespace(id=uuid4(), role=UserRole.OWNER.value, provider_id=provider_id)
    monkeypatch.setattr(
        "app.services.application_documents.create_stored_file_record",
        fake_create_stored_file_record,
    )

    with pytest.raises(HTTPException) as exc:
        await upload_application_document(
            db=db,
            application_id=application.id,
            file_content=b"%PDF",
            original_filename="consent.pdf",
            content_type="application/pdf",
            kind=DocumentFileKind.OWNER_CONSENT,
            user=owner,
        )

    assert exc.value.status_code == 409
    assert "документы можно загружать" in exc.value.detail
    assert application.status == ApplicationStatus.ACCEPTED_BY_OWNER.value
    assert db.added == []
