from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.enums import GeneratedDocumentKind
from app.models.generated_document import GeneratedDocument
from app.routers import applications as applications_router


def _make_document(
    *,
    application_id: UUID,
    document_id: UUID | None = None,
    docx_url: str | None = None,
    pdf_url: str | None = None,
    zip_url: str | None = None,
    kind: GeneratedDocumentKind = GeneratedDocumentKind.CONTRACT,
) -> GeneratedDocument:
    document = GeneratedDocument(
        id=document_id or uuid4(),
        application_id=application_id,
        kind=kind.value,
        docx_url=docx_url,
        pdf_url=pdf_url,
        zip_url=zip_url,
        generated_at=datetime.now(timezone.utc),
    )
    return document


class _FakeDB:
    def __init__(self, document: GeneratedDocument | None) -> None:
        self._document = document

    async def get(self, model, object_id):
        if self._document is None:
            return None
        if model is GeneratedDocument and object_id == self._document.id:
            return self._document
        return None


def test_download_returns_404_when_document_missing() -> None:
    db = _FakeDB(document=None)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            applications_router.download_generated_document(
                application_id=uuid4(),
                document_id=uuid4(),
                db=db,
            )
        )
    assert exc_info.value.status_code == 404
    assert "не найден" in exc_info.value.detail


def test_download_returns_404_when_document_belongs_to_another_application() -> None:
    foreign_id = uuid4()
    document = _make_document(application_id=foreign_id, docx_url="storage/contract.docx")
    db = _FakeDB(document=document)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            applications_router.download_generated_document(
                application_id=uuid4(),  # другая заявка
                document_id=document.id,
                db=db,
            )
        )
    assert exc_info.value.status_code == 404


def test_download_serves_docx_with_word_media_type(tmp_path, monkeypatch) -> None:
    application_id = uuid4()
    docx_path = tmp_path / "contract.docx"
    docx_path.write_bytes(b"PK\x03\x04 fake docx")
    document = _make_document(
        application_id=application_id, docx_url="storage/contract.docx"
    )
    db = _FakeDB(document=document)
    monkeypatch.setattr(
        "app.routers.applications.resolve_storage_file",
        lambda url: docx_path,
    )
    response = asyncio.get_event_loop().run_until_complete(
        applications_router.download_generated_document(
            application_id=application_id,
            document_id=document.id,
            db=db,
        )
    )
    assert isinstance(response, FileResponse)
    assert response.filename == "contract.docx"
    assert response.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_download_falls_back_to_zip_when_docx_missing(tmp_path, monkeypatch) -> None:
    application_id = uuid4()
    zip_path = tmp_path / "package.zip"
    zip_path.write_bytes(b"PK\x03\x04 fake zip")
    document = _make_document(
        application_id=application_id,
        docx_url="storage/missing.docx",
        zip_url="storage/package.zip",
        kind=GeneratedDocumentKind.PACKAGE_ZIP,
    )
    db = _FakeDB(document=document)

    def fake_resolve(url: str) -> Path:
        if "missing" in url:
            raise FileNotFoundError(url)
        return zip_path

    monkeypatch.setattr(
        "app.routers.applications.resolve_storage_file",
        fake_resolve,
    )
    response = asyncio.get_event_loop().run_until_complete(
        applications_router.download_generated_document(
            application_id=application_id,
            document_id=document.id,
            db=db,
        )
    )
    assert isinstance(response, FileResponse)
    assert response.media_type == "application/zip"


def test_download_returns_404_when_no_url_resolves(tmp_path, monkeypatch) -> None:
    application_id = uuid4()
    document = _make_document(
        application_id=application_id,
        docx_url="storage/missing.docx",
    )
    db = _FakeDB(document=document)
    monkeypatch.setattr(
        "app.routers.applications.resolve_storage_file",
        lambda url: (_ for _ in ()).throw(FileNotFoundError(url)),
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(
            applications_router.download_generated_document(
                application_id=application_id,
                document_id=document.id,
                db=db,
            )
        )
    assert exc_info.value.status_code == 404
    assert "недоступен" in exc_info.value.detail
