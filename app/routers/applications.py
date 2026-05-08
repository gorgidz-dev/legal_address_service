from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.enums import ApplicationStatus, ApplicationType, GuaranteeVariant
from app.models.address import Address
from app.models.application import Application
from app.models.client import Client
from app.models.generated_document import GeneratedDocument
from app.models.provider import Provider
from app.schemas.application import (
    ApplicationCreateAddressChange,
    ApplicationCreateInitial,
    ApplicationCreate,
    ApplicationRead,
    PromoteToContractRequest,
)
from app.schemas.document import (
    GeneratedDocumentRead,
    GuaranteeLetterRead,
    PackageGenerateResult,
)
from app.services.client_data import client_values_from_dadata
from app.services.dadata import DaDataError, DaDataNotConfigured, get_dadata_service
from app.services.document_generation import (
    DocumentGenerationError,
    create_guarantee_letter,
    create_package_record,
    current_egrn_extract,
    ensure_contract,
    render_contract_docx,
    render_guarantee_docx,
)
from app.services.storage import resolve_storage_file

router = APIRouter(prefix="/applications", tags=["applications"])


async def _get_provider_and_address(
    db: AsyncSession,
    provider_id: UUID,
    address_id: UUID,
) -> tuple[Provider, Address]:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Provider {provider_id} не найден")
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Address {address_id} не найден")
    if address.provider_id != provider.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Помещение не принадлежит выбранному собственнику",
        )
    return provider, address


async def _upsert_client_from_dadata(db: AsyncSession, inn: str) -> Client:
    try:
        service = get_dadata_service()
    except DaDataNotConfigured as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e

    try:
        lookup = await service.lookup(inn)
    except DaDataError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e

    if lookup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"ИНН {inn} не найден в ЕГРЮЛ")
    if (
        lookup.blockers.liquidating_or_liquidated
        or lookup.blockers.bankrupt
        or lookup.blockers.signatory_disqualified
        or lookup.blockers.is_branch
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "DaData вернула блокирующие признаки: ликвидация/банкротство/дисквалификация/филиал",
        )

    values = client_values_from_dadata(lookup)
    result = await db.execute(select(Client).where(Client.inn == lookup.inn))
    client = result.scalar_one_or_none()
    if client is None:
        client = Client(**values)
        db.add(client)
    else:
        for key, value in values.items():
            setattr(client, key, value)
    await db.flush()
    return client


async def _load_application_bundle(
    db: AsyncSession,
    application_id: UUID,
) -> tuple[Application, Provider, Address, Client | None]:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")
    provider = await db.get(Provider, application.provider_id)
    address = await db.get(Address, application.address_id)
    client = await db.get(Client, application.client_id) if application.client_id else None
    if provider is None or address is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "У заявки повреждена связь с собственником/адресом")
    return application, provider, address, client


@router.get("", response_model=list[ApplicationRead], summary="Список заявок")
async def list_applications(
    type_: ApplicationType | None = None,
    status_: ApplicationStatus | None = None,
    provider_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Application]:
    stmt = select(Application).order_by(Application.created_at.desc())
    if type_ is not None:
        stmt = stmt.where(Application.type == type_.value)
    if status_ is not None:
        stmt = stmt.where(Application.status == status_.value)
    if provider_id is not None:
        stmt = stmt.where(Application.provider_id == provider_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заявку (initial_registration | address_change)",
    description=(
        "Тело — discriminated union по полю `type`. "
        "Для `address_change` бэкенд при создании дополнительно дёргает DaData по ИНН клиента "
        "и upsert-ит запись в `clients`."
    ),
)
async def create_application(
    payload: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
) -> Application:
    _, address = await _get_provider_and_address(db, payload.provider_id, payload.address_id)

    if isinstance(payload, ApplicationCreateInitial):
        application = Application(
            type=ApplicationType.INITIAL_REGISTRATION.value,
            provider_id=payload.provider_id,
            address_id=payload.address_id,
            planned_client_name=payload.planned_client_name,
            company_name=payload.planned_client_name,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=payload.contact_email,
            contract_city=payload.contract_city,
            fns_number=payload.fns_number or address.fns_number,
            fns_city=payload.fns_city or address.fns_city,
            status=ApplicationStatus.DRAFT.value,
            expires_at=date.today() + timedelta(days=settings.initial_application_validity_days),
        )
    elif isinstance(payload, ApplicationCreateAddressChange):
        client = await _upsert_client_from_dadata(db, payload.client_inn)
        application = Application(
            type=ApplicationType.ADDRESS_CHANGE.value,
            provider_id=payload.provider_id,
            address_id=payload.address_id,
            client_id=client.id,
            company_name=client.short_name,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=payload.contact_email,
            term_months=payload.term_months,
            notice_period=payload.notice_period.value,
            has_correspondence_service=payload.has_correspondence_service,
            contract_city=payload.contract_city,
            fns_number=payload.fns_number or address.fns_number,
            fns_city=payload.fns_city or address.fns_city,
            status=ApplicationStatus.DRAFT.value,
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип заявки")

    db.add(application)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Нарушено ограничение БД: {e.orig}") from e
    await db.refresh(application)
    return application


@router.get("/{application_id}", response_model=ApplicationRead)
async def get_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Application:
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")
    return application


@router.post(
    "/{application_id}/issue-guarantee",
    response_model=GuaranteeLetterRead,
    status_code=status.HTTP_201_CREATED,
    summary="Выдать гарантийное письмо",
    description=(
        "Генерирует гарантийное письмо в варианте, соответствующем типу заявки "
        "(initial → краткая форма; address_change → полная). "
        "Заявка переходит в статус `guarantee_issued` (для initial) "
        "или продолжает свой жизненный цикл."
    ),
)
async def issue_guarantee(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> GuaranteeLetterRead:
    application, provider, address, client = await _load_application_bundle(db, application_id)
    today = date.today()
    try:
        egrn_extract = await current_egrn_extract(db, address.id)
        contract = None
        variant = GuaranteeVariant.INITIAL
        if application.type == ApplicationType.ADDRESS_CHANGE.value:
            if client is None:
                raise DocumentGenerationError("Для смены адреса не найден клиент")
            contract = await ensure_contract(db=db, application=application, address=address, today=today)
            variant = GuaranteeVariant.FULL
        guarantee = await create_guarantee_letter(
            db=db,
            application=application,
            egrn_extract=egrn_extract,
            variant=variant,
            today=today,
        )
        await render_guarantee_docx(
            db=db,
            application=application,
            provider=provider,
            address=address,
            client=client,
            guarantee=guarantee,
            contract=contract,
        )
        application.status = ApplicationStatus.GUARANTEE_ISSUED.value
        await db.commit()
        await db.refresh(guarantee)
        return guarantee
    except DocumentGenerationError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@router.post(
    "/{application_id}/promote-to-contract",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Повысить initial-заявку до договорной (после регистрации клиента)",
    description=(
        "Применимо только к заявкам типа `initial_registration` в статусе `guarantee_issued`. "
        "Создаёт новую дочернюю заявку `address_change` с заполнением клиента из DaData по ИНН "
        "и сразу ставит её в статус `contract_signed` после генерации договора."
    ),
)
async def promote_to_contract(
    application_id: UUID,
    payload: PromoteToContractRequest,
    db: AsyncSession = Depends(get_db),
) -> Application:
    parent = await db.get(Application, application_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {application_id} не найдена")
    if parent.type != ApplicationType.INITIAL_REGISTRATION.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Повысить можно только первичную заявку")

    client = await _upsert_client_from_dadata(db, payload.client_inn)
    child = Application(
        type=ApplicationType.ADDRESS_CHANGE.value,
        provider_id=parent.provider_id,
        address_id=parent.address_id,
        client_id=client.id,
        company_name=client.short_name,
        contact_name=payload.contact_name or parent.contact_name,
        contact_phone=payload.contact_phone or parent.contact_phone,
        contact_email=payload.contact_email or parent.contact_email,
        term_months=payload.term_months,
        notice_period=payload.notice_period.value,
        has_correspondence_service=payload.has_correspondence_service,
        contract_city=payload.contract_city or parent.contract_city,
        fns_number=parent.fns_number,
        fns_city=parent.fns_city,
        parent_application_id=parent.id,
        status=ApplicationStatus.DRAFT.value,
    )
    parent.status = ApplicationStatus.AWAITING_CONTRACT.value
    db.add(child)
    await db.commit()
    await db.refresh(child)
    return child


@router.post(
    "/{application_id}/generate-package",
    response_model=PackageGenerateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Сгенерировать ZIP-комплект документов",
    description=(
        "Состав ZIP зависит от типа заявки:\n"
        "- `initial_registration`: гарантийное письмо (.docx + .pdf) + выписка ЕГРН (.pdf)\n"
        "- `address_change`: договор (.docx + .pdf) + гарантийное письмо (.docx + .pdf) + выписка ЕГРН (.pdf)"
    ),
)
async def generate_package(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PackageGenerateResult:
    application, provider, address, client = await _load_application_bundle(db, application_id)
    today = date.today()
    try:
        egrn_extract = await current_egrn_extract(db, address.id)
        documents: list[GeneratedDocument] = []

        if application.type == ApplicationType.INITIAL_REGISTRATION.value:
            guarantee = await create_guarantee_letter(
                db=db,
                application=application,
                egrn_extract=egrn_extract,
                variant=GuaranteeVariant.INITIAL,
                today=today,
            )
            documents.append(
                await render_guarantee_docx(
                    db=db,
                    application=application,
                    provider=provider,
                    address=address,
                    client=None,
                    guarantee=guarantee,
                    contract=None,
                )
            )
            application.status = ApplicationStatus.GUARANTEE_ISSUED.value
        elif application.type == ApplicationType.ADDRESS_CHANGE.value:
            if client is None:
                raise DocumentGenerationError("Для смены адреса не найден клиент")
            contract = await ensure_contract(db=db, application=application, address=address, today=today)
            documents.append(
                await render_contract_docx(
                    db=db,
                    application=application,
                    provider=provider,
                    address=address,
                    client=client,
                    contract=contract,
                )
            )
            guarantee = await create_guarantee_letter(
                db=db,
                application=application,
                egrn_extract=egrn_extract,
                variant=GuaranteeVariant.FULL,
                today=today,
            )
            documents.append(
                await render_guarantee_docx(
                    db=db,
                    application=application,
                    provider=provider,
                    address=address,
                    client=client,
                    guarantee=guarantee,
                    contract=contract,
                )
            )
            application.status = ApplicationStatus.CONTRACT_SIGNED.value
        else:
            raise DocumentGenerationError("Неизвестный тип заявки")

        package = await create_package_record(
            db=db,
            application=application,
            documents=documents,
            egrn_extract=egrn_extract,
        )
        documents.append(package)
        await db.commit()

        result = await db.execute(
            select(GeneratedDocument)
            .where(GeneratedDocument.application_id == application.id)
            .order_by(GeneratedDocument.generated_at)
        )
        all_documents = list(result.scalars().all())
        return PackageGenerateResult(
            application_id=application.id,
            zip_url=package.zip_url or "",
            documents=all_documents,
        )
    except DocumentGenerationError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@router.get(
    "/{application_id}/documents",
    response_model=list[GeneratedDocumentRead],
    summary="Журнал сгенерированных документов по заявке",
)
async def list_application_documents(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[GeneratedDocument]:
    result = await db.execute(
        select(GeneratedDocument)
        .where(GeneratedDocument.application_id == application_id)
        .order_by(GeneratedDocument.generated_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/{application_id}/download-package",
    response_class=FileResponse,
    summary="Скачать последний ZIP-комплект по заявке",
)
async def download_latest_package(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    result = await db.execute(
        select(GeneratedDocument)
        .where(
            GeneratedDocument.application_id == application_id,
            GeneratedDocument.kind == "package_zip",
            GeneratedDocument.zip_url.is_not(None),
        )
        .order_by(GeneratedDocument.generated_at.desc())
        .limit(1)
    )
    document = result.scalar_one_or_none()
    if document is None or not document.zip_url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ZIP-комплект по заявке не найден")

    try:
        path = resolve_storage_file(document.zip_url)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    return FileResponse(
        path,
        filename=path.name,
        media_type="application/zip",
    )
