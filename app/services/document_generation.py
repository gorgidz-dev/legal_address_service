from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import GeneratedDocumentKind, GuaranteeVariant, TemplateKind
from app.models.address import Address
from app.models.application import Application
from app.models.client import Client
from app.models.contract import Contract
from app.models.document_template import DocumentTemplate
from app.models.egrn_extract import EgrnExtract
from app.models.generated_document import GeneratedDocument
from app.models.guarantee_letter import GuaranteeLetter
from app.models.provider import Provider
from app.services.document_context import (
    add_months_minus_one_day,
    build_contract_context,
    build_guarantee_context,
    format_money,
    money_in_words,
)
from app.services.document_package import create_package_zip
from app.services.document_renderer import render_docx_async
from app.services.storage import (
    application_storage_dir,
    create_stored_file_record,
    relative_storage_url,
)

DEFAULT_TEMPLATE_PATHS = {
    TemplateKind.CONTRACT: Path("templates/template_contract.docx"),
    TemplateKind.GUARANTEE_INITIAL: Path("templates/template_guarantee_initial.docx"),
    TemplateKind.GUARANTEE_FULL: Path("templates/template_guarantee_full.docx"),
}


class DocumentGenerationError(RuntimeError):
    pass


def template_kind_for_guarantee(variant: GuaranteeVariant) -> TemplateKind:
    if variant == GuaranteeVariant.INITIAL:
        return TemplateKind.GUARANTEE_INITIAL
    return TemplateKind.GUARANTEE_FULL


def package_document_name(kind: GeneratedDocumentKind, number: str) -> str:
    safe_number = number.replace("/", "-").replace("\\", "-")
    if kind == GeneratedDocumentKind.CONTRACT:
        return f"01_договор_{safe_number}.docx"
    if kind == GeneratedDocumentKind.GUARANTEE:
        return f"02_гарантийное_письмо_{safe_number}.docx"
    return f"package_{safe_number}.zip"


async def active_template_path(db: AsyncSession, kind: TemplateKind) -> tuple[Path, Any | None]:
    result = await db.execute(
        select(DocumentTemplate)
        .where(DocumentTemplate.kind == kind.value, DocumentTemplate.is_active.is_(True))
        .order_by(DocumentTemplate.version.desc())
        .limit(1)
    )
    template = result.scalar_one_or_none()
    if template is not None:
        return Path(template.file_url), template.id
    return DEFAULT_TEMPLATE_PATHS[kind], None


async def current_egrn_extract(db: AsyncSession, address_id: Any) -> EgrnExtract:
    result = await db.execute(
        select(EgrnExtract)
        .where(EgrnExtract.address_id == address_id, EgrnExtract.is_current.is_(True))
        .order_by(EgrnExtract.issue_date.desc())
        .limit(1)
    )
    extract = result.scalar_one_or_none()
    if extract is None:
        raise DocumentGenerationError("Для помещения нет актуальной выписки ЕГРН")
    return extract


async def next_number(db: AsyncSession, model: Any, field: Any, prefix: str, day: date) -> str:
    pattern = f"{prefix}-{day.year}-%"
    result = await db.execute(select(func.count()).select_from(model).where(field.like(pattern)))
    count = int(result.scalar_one())
    return f"{prefix}-{day.year}-{count + 1:04d}"


def price_for_application(application: Application, address: Address) -> Decimal:
    if application.term_months == 6:
        price = Decimal(address.price_6m)
    elif application.term_months == 11:
        price = Decimal(address.price_11m)
    else:
        raise DocumentGenerationError("Для договора должен быть выбран срок 6 или 11 месяцев")

    if application.has_correspondence_service and address.correspondence_price is not None:
        price += Decimal(address.correspondence_price)
    return price


async def ensure_contract(
    *,
    db: AsyncSession,
    application: Application,
    address: Address,
    today: date,
) -> Contract:
    result = await db.execute(select(Contract).where(Contract.application_id == application.id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    if application.term_months not in (6, 11):
        raise DocumentGenerationError("Договор можно создать только для заявки со сроком 6 или 11 месяцев")

    price_total = price_for_application(application, address)
    contract = Contract(
        application_id=application.id,
        number=await next_number(db, Contract, Contract.number, "ДА", today),
        contract_date=today,
        start_date=today,
        end_date=add_months_minus_one_day(today, application.term_months),
        price_total=price_total,
        price_total_in_words=money_in_words(price_total),
    )
    db.add(contract)
    await db.flush()
    return contract


async def create_guarantee_letter(
    *,
    db: AsyncSession,
    application: Application,
    egrn_extract: EgrnExtract,
    variant: GuaranteeVariant,
    today: date,
) -> GuaranteeLetter:
    guarantee = GuaranteeLetter(
        application_id=application.id,
        variant=variant.value,
        number=await next_number(db, GuaranteeLetter, GuaranteeLetter.number, "ГП", today),
        letter_date=today,
        egrn_extract_id=egrn_extract.id,
    )
    db.add(guarantee)
    await db.flush()
    return guarantee


async def render_guarantee_docx(
    *,
    db: AsyncSession,
    application: Application,
    provider: Provider,
    address: Address,
    client: Client | None,
    guarantee: GuaranteeLetter,
    contract: Contract | None,
) -> GeneratedDocument:
    variant = GuaranteeVariant(guarantee.variant)
    template_kind = template_kind_for_guarantee(variant)
    template_path, template_id = await active_template_path(db, template_kind)
    output_path = application_storage_dir(application.id) / package_document_name(
        GeneratedDocumentKind.GUARANTEE,
        guarantee.number,
    )
    context = build_guarantee_context(
        application=application,
        provider=provider,
        address=address,
        client=client,
        variant=variant,
        guarantee_number=guarantee.number,
        guarantee_date=guarantee.letter_date,
        contract_number=contract.number if contract else None,
        contract_date=contract.contract_date if contract else None,
    )
    await render_docx_async(template_path=template_path, output_path=output_path, context=context)
    await create_stored_file_record(
        db=db,
        content=output_path.read_bytes(),
        kind="guarantee_docx",
        original_filename=output_path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        client_id=client.id if client else application.client_id,
        application_id=application.id,
    )
    document = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.GUARANTEE.value,
        template_id=template_id,
        egrn_extract_id=guarantee.egrn_extract_id,
        docx_url=relative_storage_url(output_path),
    )
    db.add(document)
    await db.flush()
    return document


async def render_contract_docx(
    *,
    db: AsyncSession,
    application: Application,
    provider: Provider,
    address: Address,
    client: Client,
    contract: Contract,
) -> GeneratedDocument:
    template_path, template_id = await active_template_path(db, TemplateKind.CONTRACT)
    output_path = application_storage_dir(application.id) / package_document_name(
        GeneratedDocumentKind.CONTRACT,
        contract.number,
    )
    context = build_contract_context(
        application=application,
        provider=provider,
        address=address,
        client=client,
        contract_number=contract.number,
        contract_date=contract.contract_date,
        start_date=contract.start_date,
        price_total=Decimal(contract.price_total),
    )
    await render_docx_async(template_path=template_path, output_path=output_path, context=context)
    await create_stored_file_record(
        db=db,
        content=output_path.read_bytes(),
        kind="contract_docx",
        original_filename=output_path.name,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        client_id=client.id,
        application_id=application.id,
    )
    document = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.CONTRACT.value,
        template_id=template_id,
        docx_url=relative_storage_url(output_path),
    )
    db.add(document)
    await db.flush()
    return document


async def create_package_record(
    *,
    db: AsyncSession,
    application: Application,
    documents: list[GeneratedDocument],
    egrn_extract: EgrnExtract,
) -> GeneratedDocument:
    package_path = application_storage_dir(application.id) / f"package_{application.id}.zip"
    entries: list[tuple[Path, str]] = []

    for document in documents:
        if document.docx_url:
            path = Path(document.docx_url)
            if document.kind == GeneratedDocumentKind.CONTRACT.value:
                entries.append((path, path.name))
            elif document.kind == GeneratedDocumentKind.GUARANTEE.value:
                entries.append((path, path.name))

    entries.append((Path(egrn_extract.pdf_file_url), "03_выписка_егрн.pdf"))
    if egrn_extract.signature_file_url:
        entries.append((Path(egrn_extract.signature_file_url), "03_выписка_егрн.sig"))

    create_package_zip(zip_path=package_path, entries=entries)
    await create_stored_file_record(
        db=db,
        content=package_path.read_bytes(),
        kind="package_zip",
        original_filename=package_path.name,
        content_type="application/zip",
        client_id=application.client_id,
        application_id=application.id,
    )
    package = GeneratedDocument(
        application_id=application.id,
        kind=GeneratedDocumentKind.PACKAGE_ZIP.value,
        egrn_extract_id=egrn_extract.id,
        zip_url=relative_storage_url(package_path),
    )
    db.add(package)
    await db.flush()
    return package
