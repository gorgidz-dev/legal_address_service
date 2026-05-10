from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    AddressPublicationStatus,
    ApplicationEventKind,
    ApplicationStatus,
    ApplicationType,
    DocumentFileKind,
    NotificationAudience,
    NoticePeriod,
    UserRole,
)
from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.client import Client
from app.models.provider import Provider
from app.models.stored_file import StoredFile
from app.models.user import User
from app.schemas.demo import DemoCredential, DemoSeedCounts, DemoSeedResult
from app.services.auth_security import hash_password
from app.services.storage import create_stored_file_record

DEMO_PASSWORD = "demo12345"


def marketplace_demo_payload() -> dict[str, list[dict[str, Any]]]:
    return {
        "credentials": [
            {
                "email": "admin@uradres-demo.ru",
                "full_name": "Администратор площадки",
                "role": UserRole.ADMIN.value,
                "password": DEMO_PASSWORD,
            },
            {
                "email": "owner-msk@uradres-demo.ru",
                "full_name": "Ирина Собственник",
                "role": UserRole.OWNER.value,
                "password": DEMO_PASSWORD,
                "provider_code": "owner-msk",
            },
            {
                "email": "owner-spb@uradres-demo.ru",
                "full_name": "Павел Собственник",
                "role": UserRole.OWNER.value,
                "password": DEMO_PASSWORD,
                "provider_code": "owner-spb",
            },
            {
                "email": "client@uradres-demo.ru",
                "full_name": "Мария Клиент",
                "role": UserRole.CLIENT.value,
                "password": DEMO_PASSWORD,
            },
        ],
        "users": [
            {
                "email": "admin@uradres-demo.ru",
                "full_name": "Администратор площадки",
                "role": UserRole.ADMIN.value,
            },
            {
                "email": "owner-msk@uradres-demo.ru",
                "full_name": "Ирина Собственник",
                "role": UserRole.OWNER.value,
                "provider_code": "owner-msk",
            },
            {
                "email": "owner-spb@uradres-demo.ru",
                "full_name": "Павел Собственник",
                "role": UserRole.OWNER.value,
                "provider_code": "owner-spb",
            },
            {
                "email": "client@uradres-demo.ru",
                "full_name": "Мария Клиент",
                "role": UserRole.CLIENT.value,
            },
        ],
        "providers": [
            {
                "code": "owner-msk",
                "full_name": "ООО «Московский адресный фонд»",
                "short_name": "Московский адресный фонд",
                "inn": "7707083893",
                "kpp": "770701001",
                "ogrn": "1027700132195",
                "legal_address": "г. Москва, ул. Тверская, д. 7",
                "signatory_name": "Ирина Сергеевна Орлова",
                "signatory_position": "Генеральный директор",
                "signatory_initials": "И. С. Орлова",
                "phone": "+7 495 000-10-01",
            },
            {
                "code": "owner-spb",
                "full_name": "ООО «Невские помещения»",
                "short_name": "Невские помещения",
                "inn": "7736050003",
                "kpp": "773601001",
                "ogrn": "1027700070518",
                "legal_address": "г. Санкт-Петербург, Невский пр., д. 88",
                "signatory_name": "Павел Андреевич Кузнецов",
                "signatory_position": "Управляющий партнер",
                "signatory_initials": "П. А. Кузнецов",
                "phone": "+7 812 000-20-02",
            },
        ],
        "clients": [
            {
                "inn": "7704217370",
                "kpp": "770401001",
                "ogrn": "1027700132195",
                "full_name": "Общество с ограниченной ответственностью «Дельта Кабинет»",
                "short_name": "ООО «Дельта Кабинет»",
                "legal_address": "119019, г. Москва, ул. Новый Арбат, д. 11",
                "signatory_name": "Мария Игоревна Ковалёва",
                "signatory_position": "Генеральный директор",
                "signatory_initials": "М. И. Ковалёва",
                "email": "client@uradres-demo.ru",
                "phone": "+7 900 700-11-22",
                "egrul_status": "ACTIVE",
            },
            {
                "inn": "7736050003",
                "kpp": "773601001",
                "ogrn": "1027700070518",
                "full_name": "Общество с ограниченной ответственностью «Северный Регистр»",
                "short_name": "ООО «Северный Регистр»",
                "legal_address": "191025, г. Санкт-Петербург, Литейный пр., д. 24",
                "signatory_name": "Алексей Романович Соколов",
                "signatory_position": "Директор",
                "signatory_initials": "А. Р. Соколов",
                "email": "client@uradres-demo.ru",
                "phone": "+7 921 610-44-55",
                "egrul_status": "ACTIVE",
            },
        ],
        "addresses": [
            {
                "provider_code": "owner-msk",
                "full_address": "г. Москва, ул. Тверская, д. 7, офис 41",
                "room_number": "офис 41",
                "cadastral_number": "77:01:0001001:1001",
                "ownership_doc": "Выписка ЕГРН от 01.05.2026",
                "ownership_doc_short": "ЕГРН 01.05.2026",
                "ownership_doc_pages": 8,
                "price_6m": Decimal("18000.00"),
                "price_11m": Decimal("30000.00"),
                "correspondence_price": Decimal("3500.00"),
                "fns_number": 46,
                "fns_city": "Москве",
                "is_available": True,
                "publication_status": AddressPublicationStatus.PUBLISHED.value,
            },
            {
                "provider_code": "owner-msk",
                "full_address": "г. Москва, Пресненская наб., д. 12, помещ. 8",
                "room_number": "помещ. 8",
                "cadastral_number": "77:01:0001002:2002",
                "ownership_doc": "Выписка ЕГРН от 02.05.2026",
                "ownership_doc_short": "ЕГРН 02.05.2026",
                "ownership_doc_pages": 6,
                "price_6m": Decimal("22000.00"),
                "price_11m": Decimal("39000.00"),
                "correspondence_price": Decimal("4500.00"),
                "fns_number": 3,
                "fns_city": "Москве",
                "is_available": True,
                "publication_status": AddressPublicationStatus.MODERATION.value,
            },
            {
                "provider_code": "owner-spb",
                "full_address": "г. Санкт-Петербург, Невский пр., д. 88, офис 12",
                "room_number": "офис 12",
                "cadastral_number": "78:31:0002001:3003",
                "ownership_doc": "Выписка ЕГРН от 03.05.2026",
                "ownership_doc_short": "ЕГРН 03.05.2026",
                "ownership_doc_pages": 7,
                "price_6m": Decimal("15000.00"),
                "price_11m": Decimal("26000.00"),
                "correspondence_price": Decimal("3000.00"),
                "fns_number": 15,
                "fns_city": "Санкт-Петербургу",
                "is_available": False,
                "publication_status": AddressPublicationStatus.ARCHIVED.value,
            },
        ],
        "applications": [
            {
                "code": "demo-admin-review",
                "status": ApplicationStatus.ADMIN_REVIEW.value,
                "type": ApplicationType.INITIAL_REGISTRATION.value,
                "address_index": 0,
                "planned_client_name": "Альфа Ритейл",
                "contact_name": "Анна Белова",
                "contact_phone": "+7 900 101-20-30",
                "contact_email": "demo-admin-review@uradres-demo.ru",
            },
            {
                "code": "demo-assigned-owner",
                "status": ApplicationStatus.ASSIGNED_TO_OWNER.value,
                "type": ApplicationType.INITIAL_REGISTRATION.value,
                "address_index": 0,
                "planned_client_name": "Смена Офиса",
                "contact_name": "Григорий Савин",
                "contact_phone": "+7 900 202-30-40",
                "contact_email": "demo-assigned-owner@uradres-demo.ru",
            },
            {
                "code": "demo-accepted-owner",
                "status": ApplicationStatus.ACCEPTED_BY_OWNER.value,
                "type": ApplicationType.INITIAL_REGISTRATION.value,
                "address_index": 1,
                "planned_client_name": "Вектор Право",
                "contact_name": "Ольга Туманова",
                "contact_phone": "+7 900 303-40-50",
                "contact_email": "demo-accepted-owner@uradres-demo.ru",
            },
            {
                "code": "demo-documents-preparing",
                "status": ApplicationStatus.DOCUMENTS_PREPARING.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7704217370",
                "address_index": 0,
                "contact_name": "Мария Ковалёва",
                "contact_phone": "+7 900 700-11-22",
                "contact_email": "demo-documents-preparing@uradres-demo.ru",
                "term_months": 11,
            },
            {
                "code": "demo-documents-review",
                "status": ApplicationStatus.DOCUMENTS_REVIEW.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7704217370",
                "address_index": 0,
                "contact_name": "Мария Ковалёва",
                "contact_phone": "+7 900 700-11-22",
                "contact_email": "demo-documents-review@uradres-demo.ru",
                "term_months": 11,
            },
            {
                "code": "demo-documents-revision",
                "status": ApplicationStatus.DOCUMENTS_REVISION.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7736050003",
                "address_index": 2,
                "contact_name": "Алексей Соколов",
                "contact_phone": "+7 921 610-44-55",
                "contact_email": "demo-documents-revision@uradres-demo.ru",
                "term_months": 6,
            },
            {
                "code": "demo-ready",
                "status": ApplicationStatus.READY_FOR_CLIENT.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7704217370",
                "address_index": 0,
                "contact_name": "Мария Ковалёва",
                "contact_phone": "+7 900 700-11-22",
                "contact_email": "demo-ready@uradres-demo.ru",
                "term_months": 11,
            },
            {
                "code": "demo-completed",
                "status": ApplicationStatus.COMPLETED.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7736050003",
                "address_index": 2,
                "contact_name": "Алексей Соколов",
                "contact_phone": "+7 921 610-44-55",
                "contact_email": "demo-completed@uradres-demo.ru",
                "term_months": 6,
            },
            {
                "code": "demo-dispute",
                "status": ApplicationStatus.DISPUTE.value,
                "type": ApplicationType.ADDRESS_CHANGE.value,
                "client_inn": "7704217370",
                "address_index": 0,
                "contact_name": "Мария Ковалёва",
                "contact_phone": "+7 900 700-11-22",
                "contact_email": "demo-dispute@uradres-demo.ru",
                "term_months": 11,
            },
        ],
        "documents": [
            {
                "application_code": "demo-documents-review",
                "kind": DocumentFileKind.OWNER_CONSENT.value,
                "original_filename": "demo-owner-consent.pdf",
                "content_type": "application/pdf",
                "content": b"%PDF-1.4 demo owner consent",
                "uploaded_by": "owner-msk@uradres-demo.ru",
            },
            {
                "application_code": "demo-documents-review",
                "kind": DocumentFileKind.CONTRACT.value,
                "original_filename": "demo-contract.pdf",
                "content_type": "application/pdf",
                "content": b"%PDF-1.4 demo contract",
                "uploaded_by": "owner-msk@uradres-demo.ru",
            },
            {
                "application_code": "demo-ready",
                "kind": DocumentFileKind.ACT.value,
                "original_filename": "demo-act.pdf",
                "content_type": "application/pdf",
                "content": b"%PDF-1.4 demo act",
                "uploaded_by": "owner-msk@uradres-demo.ru",
            },
        ],
        "events": [
            {
                "application_code": "demo-documents-review",
                "kind": ApplicationEventKind.DOCUMENT_UPLOADED.value,
                "audience": NotificationAudience.ADMIN.value,
                "title": "Исполнитель загрузил документы",
                "message": "Демо-комплект ожидает ручной проверки площадки.",
            },
            {
                "application_code": "demo-documents-review",
                "kind": ApplicationEventKind.DOCUMENT_UPLOADED.value,
                "audience": NotificationAudience.OWNER.value,
                "title": "Документы отправлены",
                "message": "Комплект передан администратору на проверку.",
            },
            {
                "application_code": "demo-ready",
                "kind": ApplicationEventKind.DOCUMENT_APPROVED.value,
                "audience": NotificationAudience.CLIENT.value,
                "title": "Документы готовы",
                "message": "Демо-документы доступны клиенту в личном кабинете.",
            },
        ],
    }


def _empty_counts() -> dict[str, int]:
    return {
        "users": 0,
        "providers": 0,
        "clients": 0,
        "addresses": 0,
        "applications": 0,
        "documents": 0,
        "events": 0,
    }


def _credential_models(payload: dict[str, list[dict[str, Any]]]) -> list[DemoCredential]:
    return [DemoCredential(**credential) for credential in payload["credentials"]]


async def _one_or_none(db: AsyncSession, model, *conditions):
    result = await db.execute(select(model).where(*conditions))
    return result.scalar_one_or_none()


def _touch_stats(item: object | None, *, created: dict[str, int], updated: dict[str, int], key: str) -> None:
    if item is None:
        created[key] += 1
    else:
        updated[key] += 1


async def seed_marketplace_demo(db: AsyncSession, *, password: str = DEMO_PASSWORD) -> DemoSeedResult:
    payload = marketplace_demo_payload()
    created = _empty_counts()
    updated = _empty_counts()

    providers_by_code: dict[str, Provider] = {}
    for item in payload["providers"]:
        provider = await _one_or_none(db, Provider, Provider.code == item["code"])
        _touch_stats(provider, created=created, updated=updated, key="providers")
        if provider is None:
            provider = Provider(code=item["code"])
            db.add(provider)
        for field in (
            "full_name",
            "short_name",
            "inn",
            "kpp",
            "ogrn",
            "legal_address",
            "signatory_name",
            "signatory_position",
            "signatory_initials",
            "phone",
        ):
            setattr(provider, field, item.get(field))
        provider.is_active = True
        providers_by_code[provider.code] = provider
    await db.flush()

    users_by_email: dict[str, User] = {}
    for item in payload["credentials"]:
        user = await _one_or_none(db, User, User.email == item["email"])
        _touch_stats(user, created=created, updated=updated, key="users")
        if user is None:
            user = User(email=item["email"])
            db.add(user)
        user.full_name = item["full_name"]
        user.role = item["role"]
        user.password_hash = hash_password(password)
        user.is_active = True
        provider_code = item.get("provider_code")
        user.provider_id = providers_by_code[provider_code].id if provider_code else None
        users_by_email[user.email] = user
    await db.flush()

    clients_by_inn: dict[str, Client] = {}
    for item in payload["clients"]:
        client = await _one_or_none(db, Client, Client.inn == item["inn"])
        _touch_stats(client, created=created, updated=updated, key="clients")
        if client is None:
            client = Client(inn=item["inn"])
            db.add(client)
        for field in (
            "kpp",
            "ogrn",
            "full_name",
            "short_name",
            "legal_address",
            "signatory_name",
            "signatory_position",
            "signatory_initials",
            "email",
            "phone",
            "egrul_status",
        ):
            setattr(client, field, item.get(field))
        clients_by_inn[client.inn] = client
    await db.flush()

    addresses: list[Address] = []
    for item in payload["addresses"]:
        address = await _one_or_none(db, Address, Address.cadastral_number == item["cadastral_number"])
        _touch_stats(address, created=created, updated=updated, key="addresses")
        if address is None:
            address = Address(cadastral_number=item["cadastral_number"])
            db.add(address)
        address.provider_id = providers_by_code[item["provider_code"]].id
        for field in (
            "full_address",
            "room_number",
            "ownership_doc",
            "ownership_doc_short",
            "ownership_doc_pages",
            "price_6m",
            "price_11m",
            "correspondence_price",
            "fns_number",
            "fns_city",
            "is_available",
            "publication_status",
        ):
            setattr(address, field, item.get(field))
        if address.publication_status == AddressPublicationStatus.PUBLISHED.value:
            address.published_at = datetime.now(timezone.utc)
        addresses.append(address)
    await db.flush()

    client_user = users_by_email["client@uradres-demo.ru"]
    applications_by_code: dict[str, Application] = {}
    for item in payload["applications"]:
        application = await _one_or_none(db, Application, Application.contact_email == item["contact_email"])
        _touch_stats(application, created=created, updated=updated, key="applications")
        if application is None:
            application = Application(contact_email=item["contact_email"])
            db.add(application)

        address = addresses[item["address_index"]]
        application.type = item["type"]
        application.provider_id = address.provider_id
        application.address_id = address.id
        application.contact_name = item["contact_name"]
        application.contact_phone = item["contact_phone"]
        application.contact_email = item["contact_email"]
        application.has_correspondence_service = item.get("has_correspondence_service", False)
        application.contract_city = item.get("contract_city") or address.fns_city
        application.fns_number = address.fns_number
        application.fns_city = address.fns_city
        application.status = item["status"]
        application.created_by = client_user.id

        if item["type"] == ApplicationType.INITIAL_REGISTRATION.value:
            application.client_id = None
            application.planned_client_name = item["planned_client_name"]
            application.company_name = item["planned_client_name"]
            application.term_months = None
            application.notice_period = None
            application.expires_at = date.today() + timedelta(days=30)
        else:
            client = clients_by_inn[item["client_inn"]]
            application.client_id = client.id
            application.planned_client_name = None
            application.company_name = client.short_name
            application.term_months = item["term_months"]
            application.notice_period = NoticePeriod.ONE_MONTH.value
            application.expires_at = None

        applications_by_code[item["code"]] = application
    await db.flush()

    for item in payload["documents"]:
        application = applications_by_code[item["application_code"]]
        existing_file = await _one_or_none(
            db,
            StoredFile,
            StoredFile.application_id == application.id,
            StoredFile.kind == item["kind"],
            StoredFile.original_filename == item["original_filename"],
        )
        _touch_stats(existing_file, created=created, updated=updated, key="documents")
        if existing_file is None:
            await create_stored_file_record(
                db=db,
                content=item["content"],
                kind=item["kind"],
                original_filename=item["original_filename"],
                content_type=item["content_type"],
                application_id=application.id,
                uploaded_by=users_by_email[item["uploaded_by"]].id,
            )

    now = datetime.now(timezone.utc)
    for item in payload["events"]:
        application = applications_by_code[item["application_code"]]
        existing_event = await _one_or_none(
            db,
            ApplicationEvent,
            ApplicationEvent.application_id == application.id,
            ApplicationEvent.audience == item["audience"],
            ApplicationEvent.title == item["title"],
        )
        _touch_stats(existing_event, created=created, updated=updated, key="events")
        if existing_event is None:
            existing_event = ApplicationEvent(
                application_id=application.id,
                audience=item["audience"],
                title=item["title"],
                created_at=now,
            )
            db.add(existing_event)
        existing_event.kind = item["kind"]
        existing_event.message = item["message"]
        existing_event.payload = {"source": "demo_seed", "application_code": item["application_code"]}
        existing_event.created_by = users_by_email["admin@uradres-demo.ru"].id

    await db.flush()
    return DemoSeedResult(
        created=DemoSeedCounts(**created),
        updated=DemoSeedCounts(**updated),
        credentials=_credential_models(payload),
    )
