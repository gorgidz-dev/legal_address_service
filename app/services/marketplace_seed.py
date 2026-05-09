from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.enums import AddressPublicationStatus, ApplicationStatus, UserRole


def marketplace_demo_payload() -> dict[str, list[dict[str, Any]]]:
    return {
        "users": [
            {
                "email": "admin@uradres.test",
                "full_name": "Администратор площадки",
                "role": UserRole.ADMIN.value,
            },
            {
                "email": "owner-msk@uradres.test",
                "full_name": "Ирина Собственник",
                "role": UserRole.OWNER.value,
                "provider_code": "owner-msk",
            },
            {
                "email": "owner-spb@uradres.test",
                "full_name": "Павел Собственник",
                "role": UserRole.OWNER.value,
                "provider_code": "owner-spb",
            },
            {
                "email": "client@uradres.test",
                "full_name": "Мария Клиент",
                "role": UserRole.CLIENT.value,
            },
        ],
        "providers": [
            {
                "code": "owner-msk",
                "full_name": "ООО «Московский адресный фонд»",
                "short_name": "Московский адресный фонд",
                "inn": "7701000001",
                "phone": "+7 495 000-10-01",
            },
            {
                "code": "owner-spb",
                "full_name": "ООО «Невские помещения»",
                "short_name": "Невские помещения",
                "inn": "7801000002",
                "phone": "+7 812 000-20-02",
            },
        ],
        "addresses": [
            {
                "provider_code": "owner-msk",
                "full_address": "г. Москва, ул. Тверская, д. 7, офис 41",
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
            {"status": ApplicationStatus.ADMIN_REVIEW.value, "address_index": 0},
            {"status": ApplicationStatus.DOCUMENTS_REVIEW.value, "address_index": 0},
            {"status": ApplicationStatus.READY_FOR_CLIENT.value, "address_index": 0},
        ],
    }
