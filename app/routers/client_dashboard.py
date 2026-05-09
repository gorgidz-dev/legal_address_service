from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_client
from app.database import get_db
from app.enums import NotificationAudience
from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.provider import Provider
from app.models.user import User
from app.schemas.client_dashboard import ClientApplicationRead
from app.schemas.marketplace import ApplicationEventRead

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/applications", response_model=list[ClientApplicationRead])
async def list_client_applications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_client),
) -> list[ClientApplicationRead]:
    result = await db.execute(
        select(Application, Address, Provider)
        .join(Address, Address.id == Application.address_id)
        .join(Provider, Provider.id == Application.provider_id)
        .where(Application.created_by == user.id)
        .order_by(Application.created_at.desc())
    )
    rows = [
        (application, address, provider)
        for application, address, provider in result.all()
        if application.created_by == user.id
    ]
    application_ids = [application.id for application, _, _ in rows]
    events_by_application: dict[UUID, list[ApplicationEventRead]] = defaultdict(list)

    if application_ids:
        events_result = await db.execute(
            select(ApplicationEvent)
            .where(
                ApplicationEvent.application_id.in_(application_ids),
                ApplicationEvent.audience == NotificationAudience.CLIENT.value,
            )
            .order_by(ApplicationEvent.created_at.asc())
        )
        for event in events_result.scalars().all():
            if event.audience != NotificationAudience.CLIENT.value:
                continue
            if event.application_id not in application_ids:
                continue
            events_by_application[event.application_id].append(ApplicationEventRead.model_validate(event))

    return [
        ClientApplicationRead(
            id=application.id,
            type=application.type,
            status=application.status,
            provider_id=application.provider_id,
            address_id=application.address_id,
            provider_name=provider.short_name,
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
            events=events_by_application[application.id],
            created_at=application.created_at,
            updated_at=application.updated_at,
        )
        for application, address, provider in rows
    ]
