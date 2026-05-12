from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Optional

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.enums import (
    AddressPhotoModerationStatus,
    AddressPublicationStatus,
    ApplicationEventKind,
    ApplicationStatus,
    ApplicationType,
    NotificationAudience,
    OwnerConnectionRequestStatus,
    UserRole,
)
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.application import Application
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.user import User
from app.schemas.address_photo import AddressPhotoRead
from app.schemas.marketplace import (
    ProviderConnectionRequestCreate,
    ProviderConnectionRequestRead,
    PublicClientApplicationCreate,
    PublicClientApplicationCreateAddressChange,
    PublicClientApplicationCreateInitial,
    PublicClientApplicationResult,
    PublicAddressRead,
)
from app.routers.applications import _upsert_client_from_dadata
from app.schemas.application import ApplicationRead
from app.schemas.auth import CurrentUserRead
from app.services.address_photos import photo_to_public_dict
from app.services.auth_security import hash_password_async
from app.services.auth_sessions import create_session, extract_request_metadata
from app.services.user_create import try_persist_user
from app.services.rate_limit import (
    PROVIDER_REQUEST_RULES,
    PUBLIC_APPLICATION_RULES,
    assert_within_rate_limit,
    record_attempt,
)
from app.services.notification_events import create_application_event

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def public_address_from_row(
    *,
    address: Address,
    provider: Provider,
    term_months: Literal[6, 11] = 11,
    photos: list[AddressPhoto] | None = None,
) -> PublicAddressRead:
    selected_price: Decimal = address.price_6m if term_months == 6 else address.price_11m
    photo_models = [
        AddressPhotoRead.model_validate(photo_to_public_dict(p)) for p in (photos or [])
    ]
    main_url: Optional[str] = next(
        (p.url for p in photo_models if p.is_main),
        photo_models[0].url if photo_models else None,
    )
    return PublicAddressRead(
        id=address.id,
        provider_id=address.provider_id,
        provider_name=provider.short_name,
        full_address=address.full_address,
        room_number=address.room_number,
        price_6m=address.price_6m,
        price_11m=address.price_11m,
        selected_price=selected_price,
        correspondence_price=address.correspondence_price,
        fns_number=address.fns_number,
        fns_city=address.fns_city,
        is_available=address.is_available,
        publication_status=address.publication_status,
        created_at=address.created_at,
        updated_at=address.updated_at,
        photos=photo_models,
        main_photo_url=main_url,
    )


async def _load_approved_photos_for(
    db: AsyncSession,
    address_ids: list,
) -> dict:
    """Возвращает {address_id: [AddressPhoto, ...]} только для approved-фото."""
    if not address_ids:
        return {}
    result = await db.execute(
        select(AddressPhoto)
        .where(
            AddressPhoto.address_id.in_(address_ids),
            AddressPhoto.moderation_status == AddressPhotoModerationStatus.APPROVED.value,
        )
        .order_by(AddressPhoto.is_main.desc(), AddressPhoto.sort_order, AddressPhoto.created_at)
    )
    photos_by_address: dict = {}
    for photo in result.scalars().all():
        photos_by_address.setdefault(photo.address_id, []).append(photo)
    return photos_by_address


@router.get("/addresses", response_model=list[PublicAddressRead])
async def public_addresses(
    city: Annotated[Optional[str], Query(max_length=120)] = None,
    fns_number: Annotated[Optional[int], Query(ge=1, le=9999)] = None,
    term_months: Annotated[int, Query()] = 11,
    correspondence: Annotated[Optional[bool], Query()] = None,
    db: AsyncSession = Depends(get_db),
) -> list[PublicAddressRead]:
    if term_months not in (6, 11):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="term_months must be 6 or 11")

    stmt = (
        select(Address, Provider)
        .join(Provider, Provider.id == Address.provider_id)
        .where(
            Provider.is_active.is_(True),
            Address.is_available.is_(True),
            Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
        )
        .order_by(Address.full_address)
    )
    if city:
        stmt = stmt.where(Address.full_address.ilike(f"%{city.strip()}%"))
    if fns_number is not None:
        stmt = stmt.where(Address.fns_number == fns_number)
    if correspondence is True:
        stmt = stmt.where(Address.correspondence_price.is_not(None))

    result = await db.execute(stmt)
    rows = list(result.all())
    photos_by_address = await _load_approved_photos_for(db, [a.id for a, _ in rows])
    return [
        public_address_from_row(
            address=address,
            provider=provider,
            term_months=6 if term_months == 6 else 11,
            photos=photos_by_address.get(address.id),
        )
        for address, provider in rows
    ]


@router.post(
    "/provider-requests",
    response_model=ProviderConnectionRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_request(
    payload: ProviderConnectionRequestCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProviderConnectionRequest:
    _, ip = extract_request_metadata(request)
    keys = {"ip": ip}
    await assert_within_rate_limit(db, PROVIDER_REQUEST_RULES, keys)

    new_request = ProviderConnectionRequest(
        **payload.model_dump(),
        status=OwnerConnectionRequestStatus.NEW.value,
    )
    db.add(new_request)
    await record_attempt(db, "provider_request", keys, succeeded=True)
    await db.commit()
    await db.refresh(new_request)
    return new_request


async def _published_address_bundle(db: AsyncSession, address_id) -> tuple[Address, Provider]:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    provider = await db.get(Provider, address.provider_id)
    if provider is None or not provider.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Собственник адреса не найден или отключён")
    if not address.is_available or address.publication_status != AddressPublicationStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Адрес сейчас недоступен для заявки")
    return address, provider


@router.post(
    "/applications",
    response_model=PublicClientApplicationResult,
    status_code=status.HTTP_201_CREATED,
)
async def create_public_client_application(
    payload: PublicClientApplicationCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> PublicClientApplicationResult:
    ua, ip = extract_request_metadata(request)
    keys = {"ip": ip}
    await assert_within_rate_limit(db, PUBLIC_APPLICATION_RULES, keys)

    address, provider = await _published_address_bundle(db, payload.address_id)
    if payload.has_correspondence_service and address.correspondence_price is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Для адреса не подключена корреспонденция")

    email = payload.contact_email  # already normalised by Email type
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")

    user = User(
        email=email,
        full_name=payload.contact_name,
        password_hash=await hash_password_async(payload.password),
        role=UserRole.CLIENT.value,
        is_active=True,
    )
    if not await try_persist_user(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким e-mail уже существует")
    await create_session(db=db, user=user, response=response, user_agent=ua, ip_address=ip)
    await record_attempt(db, "public_application", keys, succeeded=True)

    if isinstance(payload, PublicClientApplicationCreateInitial):
        application = Application(
            type=ApplicationType.INITIAL_REGISTRATION.value,
            provider_id=provider.id,
            address_id=address.id,
            planned_client_name=payload.planned_client_name,
            company_name=payload.planned_client_name,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=email,
            term_months=payload.term_months,
            has_correspondence_service=payload.has_correspondence_service,
            contract_city=payload.contract_city,
            fns_number=address.fns_number,
            fns_city=address.fns_city,
            status=ApplicationStatus.ADMIN_REVIEW.value,
            expires_at=date.today() + timedelta(days=settings.initial_application_validity_days),
            created_by=user.id,
        )
    elif isinstance(payload, PublicClientApplicationCreateAddressChange):
        client = await _upsert_client_from_dadata(db, payload.client_inn)
        application = Application(
            type=ApplicationType.ADDRESS_CHANGE.value,
            provider_id=provider.id,
            address_id=address.id,
            client_id=client.id,
            company_name=client.short_name,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            contact_email=email,
            term_months=payload.term_months,
            notice_period=payload.notice_period.value,
            has_correspondence_service=payload.has_correspondence_service,
            contract_city=payload.contract_city,
            fns_number=address.fns_number,
            fns_city=address.fns_city,
            status=ApplicationStatus.ADMIN_REVIEW.value,
            created_by=user.id,
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип заявки")

    db.add(application)
    try:
        await db.flush()
        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.CREATED,
            audience=NotificationAudience.CLIENT,
            title="Заявка создана",
            message="Заявка отправлена администратору на ручную проверку.",
            payload={"status": ApplicationStatus.ADMIN_REVIEW.value},
            created_by=user.id,
        )
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Нарушено ограничение БД: {e.orig}") from e
    await db.refresh(user)
    await db.refresh(application)
    return PublicClientApplicationResult(
        user=CurrentUserRead.model_validate(user),
        application=ApplicationRead.model_validate(application),
    )
