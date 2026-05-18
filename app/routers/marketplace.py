from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Optional
from uuid import UUID

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, literal_column, select
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
    PaymentPayerType,
    PaymentProvider,
    PaymentStatus,
    ReviewStatus,
    UserRole,
)
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.address_review import AddressReview
from app.models.address_service import AddressService
from app.models.fns_office import FnsOffice
from app.models.application import Application
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.user import User
from app.schemas.address_photo import AddressPhotoRead
from app.schemas.marketplace import (
    ProviderConnectionRequestCreate,
    ProviderConnectionRequestRead,
    PublicAddressServiceRead,
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


def _compute_amount_kopeks(address: Address, application: Application) -> int:
    """Сумма к оплате: цена за выбранный срок + опц. почта, в копейках.

    Корреспонденция тарифицируется помесячно и оплачивается на весь срок
    выбранного договора (6 или 11 мес.).
    """
    from decimal import Decimal
    term = application.term_months or 11
    base: Decimal = address.price_6m if term == 6 else address.price_11m
    total = base
    if application.has_correspondence_service and address.correspondence_price is not None:
        total += address.correspondence_price * term
    return int((total * 100).quantize(Decimal("1")))


def _pay_for_label(application: Application) -> str:
    name = application.company_name or application.planned_client_name or "Юридический адрес"
    return f"Юр. адрес: {name}"[:100]


def public_address_from_row(
    *,
    address: Address,
    provider: Provider,
    term_months: Literal[6, 11] = 11,
    photos: list[AddressPhoto] | None = None,
    services: list[AddressService] | None = None,
    rating: tuple[float | None, int] = (None, 0),
) -> PublicAddressRead:
    selected_price: Decimal = address.price_6m if term_months == 6 else address.price_11m
    photo_models = [
        AddressPhotoRead.model_validate(photo_to_public_dict(p)) for p in (photos or [])
    ]
    main_url: Optional[str] = next(
        (p.url for p in photo_models if p.is_main),
        photo_models[0].url if photo_models else None,
    )
    service_models = [
        PublicAddressServiceRead.model_validate(s) for s in (services or []) if s.is_active
    ]
    return PublicAddressRead(
        id=address.id,
        provider_id=address.provider_id,
        provider_name=provider.short_name,
        full_address=address.full_address,
        room_number=address.room_number,
        description=getattr(address, "description", None),
        price_6m=address.price_6m,
        price_11m=address.price_11m,
        selected_price=selected_price,
        correspondence_price=address.correspondence_price,
        fns_number=address.fns_number,
        fns_city=address.fns_city,
        latitude=(
            float(lat)
            if (lat := getattr(address, "latitude", None)) is not None
            else None
        ),
        longitude=(
            float(lon)
            if (lon := getattr(address, "longitude", None)) is not None
            else None
        ),
        is_available=address.is_available,
        publication_status=address.publication_status,
        created_at=address.created_at,
        updated_at=address.updated_at,
        photos=photo_models,
        main_photo_url=main_url,
        services=service_models,
        rating_avg=rating[0],
        rating_count=rating[1],
    )


async def _load_rating_aggregates_for(
    db: AsyncSession,
    address_ids: list,
) -> dict:
    """Возвращает {address_id: (avg_rating, count)} по ОПУБЛИКОВАННЫМ отзывам.

    Адреса без опубликованных отзывов в словарь не попадают —
    public_address_from_row подставит дефолт (None, 0).
    """
    if not address_ids:
        return {}
    result = await db.execute(
        select(
            AddressReview.address_id,
            func.avg(AddressReview.rating),
            func.count(AddressReview.id),
        )
        .where(
            AddressReview.address_id.in_(address_ids),
            AddressReview.status == ReviewStatus.PUBLISHED.value,
        )
        .group_by(AddressReview.address_id)
    )
    out: dict = {}
    for address_id, avg_rating, count in result.all():
        out[address_id] = (round(float(avg_rating), 2), int(count))
    return out


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


async def _load_active_services_for(
    db: AsyncSession,
    address_ids: list,
) -> dict:
    """Возвращает {address_id: [AddressService, ...]} только активные."""
    if not address_ids:
        return {}
    result = await db.execute(
        select(AddressService)
        .where(
            AddressService.address_id.in_(address_ids),
            AddressService.is_active.is_(True),
        )
        .order_by(AddressService.kind)
    )
    by_address: dict = {}
    for svc in result.scalars().all():
        by_address.setdefault(svc.address_id, []).append(svc)
    return by_address


@router.get("/fns-options")
async def public_fns_options(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """ИФНС-коды, реально присутствующие в опубликованном каталоге, с количеством адресов.

    Фронт использует это вместо хардкода 37 московских ИФНС в publicCatalog.tsx.
    Возвращает отсортированный список вида:
        [{"fns_number": 4, "fns_city": "Москва", "count": 3}, ...]
    Без счётчика 0 (если по ИФНС нет опубликованных адресов — её просто нет в выдаче).
    """
    stmt = (
        select(
            Address.fns_number,
            Address.fns_city,
            func.count(Address.id).label("count"),
        )
        .join(Provider, Provider.id == Address.provider_id)
        .where(
            Provider.is_active.is_(True),
            Address.is_available.is_(True),
            Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
            Address.fns_number.is_not(None),
        )
        .group_by(Address.fns_number, Address.fns_city)
        .order_by(func.count(Address.id).desc(), Address.fns_number.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"fns_number": row.fns_number, "fns_city": row.fns_city, "count": row.count}
        for row in rows
    ]


@router.get("/geo")
async def public_geo_tree(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Дерево Регион → Город → ИФНС по опубликованному каталогу.

    Используется каскадным фильтром: фронт грузит дерево один раз и каскадит
    в памяти. В выдаче только то, где реально есть опубликованные адреса.
    Возвращает:
        [{"region": "Москва", "count": 12, "cities": [
            {"city": "Москва", "count": 12, "offices": [
                {"id": "...", "short_number": 46, "name": "...", "count": 4}]}]}]
    """
    stmt = (
        select(
            FnsOffice.region,
            FnsOffice.city,
            FnsOffice.id,
            FnsOffice.short_number,
            FnsOffice.name,
            func.count(Address.id).label("count"),
        )
        .join(Address, Address.fns_office_id == FnsOffice.id)
        .join(Provider, Provider.id == Address.provider_id)
        .where(
            Provider.is_active.is_(True),
            Address.is_available.is_(True),
            Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
        )
        .group_by(
            FnsOffice.region,
            FnsOffice.city,
            FnsOffice.id,
            FnsOffice.short_number,
            FnsOffice.name,
        )
        .order_by(FnsOffice.region, FnsOffice.city, FnsOffice.short_number)
    )
    rows = (await db.execute(stmt)).all()

    # Сворачиваем плоские строки в дерево region → city → offices.
    regions: dict = {}
    for region, city, office_id, short_number, name, count in rows:
        reg = regions.setdefault(
            region, {"region": region, "count": 0, "_cities": {}}
        )
        reg["count"] += count
        cit = reg["_cities"].setdefault(
            city, {"city": city, "count": 0, "offices": []}
        )
        cit["count"] += count
        cit["offices"].append(
            {
                "id": str(office_id),
                "short_number": short_number,
                "name": name,
                "count": count,
            }
        )
    return [
        {
            "region": reg["region"],
            "count": reg["count"],
            "cities": list(reg["_cities"].values()),
        }
        for reg in regions.values()
    ]


@router.get("/addresses/search")
async def public_addresses_search(
    q: Annotated[Optional[str], Query(max_length=200)] = None,
    city: Annotated[Optional[str], Query(max_length=120)] = None,
    fns_number: Annotated[Optional[int], Query(ge=1, le=9999)] = None,
    region: Annotated[Optional[str], Query(max_length=120)] = None,
    geo_city: Annotated[Optional[str], Query(max_length=120)] = None,
    fns_office_id: Annotated[Optional[UUID], Query()] = None,
    correspondence: Annotated[Optional[bool], Query()] = None,
    price_lt: Annotated[Optional[int], Query(ge=0, le=10_000_000)] = None,
    price_gte: Annotated[Optional[int], Query(ge=0, le=10_000_000)] = None,
    sort: Annotated[
        Literal["relevance", "default", "price_asc", "price_desc", "newest"], Query()
    ] = "relevance",
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
    term_months: Annotated[int, Query()] = 11,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Серверный FTS по каталогу с пагинацией.

    Отличия от `/addresses`:
    - `q` — полнотекстовый поиск через PG `tsvector(russian)` с нормализацией ё→е.
      Russian-config делает stemming: "тверская" находит "тверской/тверскую/...".
    - `sort=relevance` (default) — `ts_rank_cd` если есть `q`, иначе по адресу.
    - Пагинация: `page` + `page_size`. Возвращает `{items, total, page, page_size}`.
    - Использует GIN-индекс `ix_addresses_search_tsv` (см. миграцию 0021).

    Старый `GET /addresses` остаётся для back-compat (mobile, тесты).
    """
    if term_months not in (6, 11):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="term_months must be 6 or 11",
        )

    # Базовые фильтры — те же, что в /addresses.
    base_where = [
        Provider.is_active.is_(True),
        Address.is_available.is_(True),
        Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
    ]
    if city:
        base_where.append(Address.full_address.ilike(f"%{city.strip()}%"))
    if fns_number is not None:
        base_where.append(Address.fns_number == fns_number)
    if fns_office_id is not None:
        base_where.append(Address.fns_office_id == fns_office_id)
    # Гео-каскад Регион→Город — фильтр через справочник fns_offices.
    geo_join_needed = bool(region) or bool(geo_city)
    if region:
        base_where.append(FnsOffice.region == region)
    if geo_city:
        base_where.append(FnsOffice.city == geo_city)
    if correspondence is True:
        base_where.append(Address.correspondence_price.is_not(None))
    if price_lt is not None:
        base_where.append(Address.price_11m < price_lt)
    if price_gte is not None:
        base_where.append(Address.price_11m >= price_gte)

    # FTS-запрос. Нормализуем `q` так же, как нормализуется search_tsv в БД —
    # lower + ё→е. Stemming (тверская → тверск-) делает PG-config russian.
    normalized_q = (q or "").strip().lower().replace("ё", "е")
    has_query = bool(normalized_q)

    if has_query:
        # plainto_tsquery игнорирует пунктуацию и шум — пользователь пишет
        # "ул. Тверская, д. 7" → ts-query: "ул & тверская & д & 7".
        ts_query = func.plainto_tsquery("russian", normalized_q)
        ts_vector = literal_column("search_tsv")
        base_where.append(ts_vector.op("@@")(ts_query))

    stmt = (
        select(Address, Provider)
        .join(Provider, Provider.id == Address.provider_id)
        .where(*base_where)
    )
    if geo_join_needed:
        stmt = stmt.join(FnsOffice, FnsOffice.id == Address.fns_office_id)

    # Сортировка.
    if has_query and sort == "relevance":
        stmt = stmt.order_by(
            func.ts_rank_cd(literal_column("search_tsv"), ts_query).desc(),
            Address.full_address.asc(),
        )
    elif sort == "price_asc":
        stmt = stmt.order_by(Address.price_11m.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Address.price_11m.desc())
    elif sort == "newest":
        stmt = stmt.order_by(Address.created_at.desc())
    else:
        stmt = stmt.order_by(Address.full_address.asc())

    # Total — отдельный count-query с тем же набором фильтров.
    count_stmt = (
        select(func.count())
        .select_from(Address)
        .join(Provider, Provider.id == Address.provider_id)
        .where(*base_where)
    )
    if geo_join_needed:
        count_stmt = count_stmt.join(
            FnsOffice, FnsOffice.id == Address.fns_office_id
        )

    total = (await db.execute(count_stmt)).scalar_one()

    # Пагинация.
    offset = (page - 1) * page_size
    stmt = stmt.limit(page_size).offset(offset)
    rows = list((await db.execute(stmt)).all())

    address_ids = [a.id for a, _ in rows]
    photos_by_address = await _load_approved_photos_for(db, address_ids)
    services_by_address = await _load_active_services_for(db, address_ids)
    ratings_by_address = await _load_rating_aggregates_for(db, address_ids)

    items = [
        public_address_from_row(
            address=address,
            provider=provider,
            term_months=6 if term_months == 6 else 11,
            photos=photos_by_address.get(address.id),
            services=services_by_address.get(address.id),
            rating=ratings_by_address.get(address.id, (None, 0)),
        )
        for address, provider in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


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
    address_ids = [a.id for a, _ in rows]
    photos_by_address = await _load_approved_photos_for(db, address_ids)
    services_by_address = await _load_active_services_for(db, address_ids)
    ratings_by_address = await _load_rating_aggregates_for(db, address_ids)
    return [
        public_address_from_row(
            address=address,
            provider=provider,
            term_months=6 if term_months == 6 else 11,
            photos=photos_by_address.get(address.id),
            services=services_by_address.get(address.id),
            rating=ratings_by_address.get(address.id, (None, 0)),
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
            status=ApplicationStatus.AWAITING_PAYMENT.value,
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
            status=ApplicationStatus.AWAITING_PAYMENT.value,
            created_by=user.id,
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Неизвестный тип заявки")

    db.add(application)
    try:
        await db.flush()

        # Платёжный flow: для физика — SBP инициируется отдельным /payments/initiate.
        # Для юр.лица (только в address_change) — создаём manual_invoice плейсхолдер
        # сразу, чтобы admin/owner видел заявку с ожидающим счётом.
        is_juridical = (
            isinstance(payload, PublicClientApplicationCreateAddressChange)
            and payload.payer_type == PaymentPayerType.JURIDICAL
        )
        if is_juridical:
            amount_kopeks = _compute_amount_kopeks(address, application)
            invoice_payment = Payment(
                application_id=application.id,
                provider=PaymentProvider.MANUAL_INVOICE.value,
                payer_type=PaymentPayerType.JURIDICAL.value,
                status=PaymentStatus.AWAITING_USER.value,
                amount_kopeks=amount_kopeks,
                currency="RUR",
                pay_for=_pay_for_label(application),
                initiated_by=user.id,
            )
            db.add(invoice_payment)
            await db.flush()
            create_message = (
                "Собственник загрузит счёт. После оплаты администратор подтвердит платёж вручную."
            )
        else:
            create_message = (
                "Оплатите заявку через СБП, чтобы передать её администратору на проверку."
            )

        await create_application_event(
            db=db,
            application_id=application.id,
            kind=ApplicationEventKind.CREATED,
            audience=NotificationAudience.CLIENT,
            title="Заявка создана",
            message=create_message,
            payload={"status": ApplicationStatus.AWAITING_PAYMENT.value},
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
