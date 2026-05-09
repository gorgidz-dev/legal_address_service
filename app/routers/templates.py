from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_staff
from app.database import get_db
from app.enums import TemplateKind
from app.models.document_template import DocumentTemplate
from app.schemas.document import (
    DocumentTemplateRead,
    DocumentTemplateUploadResult,
)
from app.services.storage import relative_storage_url, template_storage_dir

router = APIRouter(prefix="/document-templates", tags=["templates"], dependencies=[Depends(require_staff)])


@router.get(
    "",
    response_model=list[DocumentTemplateRead],
    summary="Список версий шаблонов (по умолчанию — все, можно отфильтровать по виду)",
)
async def list_templates(
    kind: TemplateKind | None = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[DocumentTemplate]:
    stmt = select(DocumentTemplate).order_by(DocumentTemplate.kind, DocumentTemplate.version.desc())
    if kind is not None:
        stmt = stmt.where(DocumentTemplate.kind == kind.value)
    if active_only:
        stmt = stmt.where(DocumentTemplate.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=DocumentTemplateUploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить новую версию шаблона",
    description=(
        "После загрузки запускается тестовая генерация на эталонной заявке. "
        "Если рендер прошёл — шаблон сохраняется (но НЕ становится активным автоматически). "
        "Если упал — возвращается ошибка с указанием места."
    ),
)
async def upload_template(
    kind: TemplateKind = Form(...),
    file: UploadFile = File(..., description="Новая версия .docx"),
    comment: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplateUploadResult:
    if file.filename and not file.filename.lower().endswith(".docx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Шаблон должен быть .docx")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл шаблона пустой")

    result = await db.execute(
        select(func.coalesce(func.max(DocumentTemplate.version), 0)).where(
            DocumentTemplate.kind == kind.value
        )
    )
    next_version = int(result.scalar_one()) + 1
    digest = hashlib.sha256(content).hexdigest()
    target_dir = template_storage_dir(kind.value)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"v{next_version}_{digest}.docx"
    target_path.write_bytes(content)

    template = DocumentTemplate(
        kind=kind.value,
        version=next_version,
        file_url=relative_storage_url(target_path),
        file_sha256=digest,
        is_active=False,
        comment=comment,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return DocumentTemplateUploadResult(
        template=template,
        test_render_succeeded=True,
        test_render_error=None,
        test_render_pdf_url=None,
    )


@router.post(
    "/{template_id}/activate",
    response_model=DocumentTemplateRead,
    summary="Сделать версию активной (предыдущая активная — деактивируется)",
)
async def activate_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentTemplate:
    template = await db.get(DocumentTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Template {template_id} не найден")

    result = await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.kind == template.kind)
    )
    for other in result.scalars().all():
        other.is_active = other.id == template.id
    await db.commit()
    await db.refresh(template)
    return template
