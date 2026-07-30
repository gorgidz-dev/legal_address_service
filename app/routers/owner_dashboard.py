from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_owner
from app.database import get_db
from app.enums import ADDRESS_AMENITY_VALUES, NotificationAudience, UserRole
from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.provider import Provider
from app.models.user import User
from app.schemas.marketplace import ApplicationEventRead
from app.schemas.owner_dashboard import OwnerAddressRead, OwnerApplicationRead, OwnerDashboardRead
from app.schemas.lease_calendar import LeaseCalendarItem
from app.services.lease_calendar import lease_calendar_for_owner
from app.schemas.owner_stats import OwnerAddressStats
from app.services.owner_address_stats import address_stats_for_owner
from app.schemas.provider import ProviderRead
from app.services.marketplace_status import role_actions_for_status

router = APIRouter(prefix="/owner", tags=["owner"])

OWNER_VISIBLE_STATUSES = {
    "assigned_to_owner",
    "accepted_by_owner",
    "rejected_by_owner",
    "documents_preparing",
    "documents_uploaded",
    "documents_review",
    "documents_revision",
    "ready_for_client",
    "completed",
    "cancelled",
    "dispute",
}


@router.get("/dashboard", response_model=OwnerDashboardRead)
async def get_owner_dashboard(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> OwnerDashboardRead:
    if user.provider_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Собственник не привязан к организации исполнителя")

    provider = await db.get(Provider, user.provider_id)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Организация исполнителя не найдена")
    if not provider.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Организация исполнителя отключена")

    addresses_result = await db.execute(
        select(Address)
        .where(Address.provider_id == user.provider_id)
        .order_by(Address.full_address)
    )
    addresses = [
        address
        for address in addresses_result.scalars().all()
        if address.provider_id == user.provider_id
    ]

    applications_result = await db.execute(
        select(Application, Address)
        .join(Address, Address.id == Application.address_id)
        .where(
            Application.provider_id == user.provider_id,
            Application.status.in_(OWNER_VISIBLE_STATUSES),
        )
        .order_by(Application.created_at.desc())
    )
    rows = [
        (application, address)
        for application, address in applications_result.all()
        if application.provider_id == user.provider_id
        and address.provider_id == user.provider_id
        and application.status in OWNER_VISIBLE_STATUSES
    ]

    application_ids = [application.id for application, _ in rows]
    events_by_application: dict[UUID, list[ApplicationEventRead]] = defaultdict(list)
    if application_ids:
        events_result = await db.execute(
            select(ApplicationEvent)
            .where(
                ApplicationEvent.application_id.in_(application_ids),
                ApplicationEvent.audience == NotificationAudience.OWNER.value,
            )
            .order_by(ApplicationEvent.created_at.asc())
        )
        for event in events_result.scalars().all():
            if event.audience != NotificationAudience.OWNER.value:
                continue
            if event.application_id not in application_ids:
                continue
            events_by_application[event.application_id].append(ApplicationEventRead.model_validate(event))

    return OwnerDashboardRead(
        provider=ProviderRead.model_validate(provider),
        addresses=[OwnerAddressRead.model_validate(address) for address in addresses],
        applications=[
            OwnerApplicationRead(
                id=application.id,
                type=application.type,
                status=application.status,
                provider_id=application.provider_id,
                address_id=application.address_id,
                full_address=address.full_address,
                room_number=address.room_number,
                client_id=application.client_id,
                planned_client_name=application.planned_client_name,
                company_name=application.company_name,
                contact_name=application.contact_name,
                contact_phone=application.contact_phone,
                contact_email=application.contact_email,
                term_months=application.term_months,
                notice_period=application.notice_period,
                has_correspondence_service=application.has_correspondence_service,
                contract_city=application.contract_city,
                fns_number=application.fns_number,
                fns_city=application.fns_city,
                expires_at=application.expires_at,
                parent_application_id=application.parent_application_id,
                selected_price=address.price_6m if application.term_months == 6 else address.price_11m,
                correspondence_price=address.correspondence_price,
                available_actions=role_actions_for_status(UserRole.OWNER, application.status),
                events=events_by_application[application.id],
                sla_due_at=application.sla_due_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
            )
            for application, address in rows
        ],
    )


class AddressDescriptionUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=4000)


@router.patch("/addresses/{address_id}/description")
async def update_address_description(
    address_id: UUID,
    payload: AddressDescriptionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> dict:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    if address.provider_id != user.provider_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Адрес не принадлежит вашей организации")
    address.description = (payload.description or "").strip() or None
    await db.commit()
    await db.refresh(address)
    return {"id": str(address.id), "description": address.description}


class AddressAmenitiesUpdate(BaseModel):
    """Характеристики помещения со слов собственника.

    Отдельным эндпоинтом, а не полем описания: описание — свободный текст с
    ручным сохранением, а галочки должны применяться сразу по клику.
    """

    amenities: list[str] = Field(default_factory=list)

    @field_validator("amenities")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(ADDRESS_AMENITY_VALUES))
        if unknown:
            raise ValueError(f"Неизвестные характеристики: {', '.join(unknown)}")
        seen: set[str] = set()
        return [x for x in value if not (x in seen or seen.add(x))]


@router.patch("/addresses/{address_id}/amenities")
async def update_address_amenities(
    address_id: UUID,
    payload: AddressAmenitiesUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> dict:
    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    if address.provider_id != user.provider_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Адрес не принадлежит вашей организации")
    address.amenities = list(payload.amenities)
    await db.commit()
    await db.refresh(address)
    return {"id": str(address.id), "amenities": list(address.amenities or [])}


@router.get(
    "/lease-calendar",
    response_model=list[LeaseCalendarItem],
    summary="Календарь аренды собственника",
)
async def owner_lease_calendar(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[LeaseCalendarItem]:
    if user.provider_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Собственник не привязан к организации исполнителя",
        )
    return await lease_calendar_for_owner(db=db, provider_id=user.provider_id)


@router.get(
    "/address-stats",
    response_model=list[OwnerAddressStats],
    summary="Отдача по адресам: заявки, сделки, выручка",
)
async def owner_address_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_owner),
) -> list[OwnerAddressStats]:
    if user.provider_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Собственник не привязан к организации исполнителя",
        )
    stats = await address_stats_for_owner(db=db, provider_id=user.provider_id)
    # Сортировка «сверху то, что приносит больше» — она же порядок по умолчанию
    # в кабинете, отдельного «топа» заводить не нужно.
    return sorted(stats.values(), key=lambda item: item.revenue, reverse=True)
