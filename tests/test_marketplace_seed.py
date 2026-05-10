from __future__ import annotations

from app.enums import AddressPublicationStatus, ApplicationStatus, DocumentFileKind, NotificationAudience, UserRole
from app.services.marketplace_seed import DEMO_PASSWORD, marketplace_demo_payload


def test_marketplace_demo_payload_has_required_roles_and_addresses() -> None:
    payload = marketplace_demo_payload()

    roles = {user["role"] for user in payload["users"]}
    assert UserRole.ADMIN.value in roles
    assert UserRole.OWNER.value in roles
    assert UserRole.CLIENT.value in roles
    assert len(payload["providers"]) >= 2
    assert len(payload["addresses"]) >= 3


def test_marketplace_demo_payload_has_moderation_and_application_states() -> None:
    payload = marketplace_demo_payload()

    address_statuses = {address["publication_status"] for address in payload["addresses"]}
    application_statuses = {application["status"] for application in payload["applications"]}

    assert AddressPublicationStatus.PUBLISHED.value in address_statuses
    assert AddressPublicationStatus.MODERATION.value in address_statuses
    assert ApplicationStatus.ADMIN_REVIEW.value in application_statuses
    assert ApplicationStatus.DOCUMENTS_REVIEW.value in application_statuses
    assert ApplicationStatus.READY_FOR_CLIENT.value in application_statuses


def test_marketplace_demo_payload_has_accounts_for_all_roles() -> None:
    payload = marketplace_demo_payload()

    credentials = payload["credentials"]
    roles = {credential["role"] for credential in credentials}

    assert roles == {
        UserRole.ADMIN.value,
        UserRole.OWNER.value,
        UserRole.CLIENT.value,
    }
    assert {credential["password"] for credential in credentials} == {DEMO_PASSWORD}
    assert "admin@uradres-demo.ru" in {credential["email"] for credential in credentials}


def test_marketplace_demo_payload_covers_workflow_documents_and_events() -> None:
    payload = marketplace_demo_payload()

    application_codes = {application["code"] for application in payload["applications"]}
    application_statuses = {application["status"] for application in payload["applications"]}
    document_kinds = {document["kind"] for document in payload["documents"]}
    event_audiences = {event["audience"] for event in payload["events"]}

    assert application_statuses.issuperset(
        {
            ApplicationStatus.ADMIN_REVIEW.value,
            ApplicationStatus.ASSIGNED_TO_OWNER.value,
            ApplicationStatus.ACCEPTED_BY_OWNER.value,
            ApplicationStatus.DOCUMENTS_PREPARING.value,
            ApplicationStatus.DOCUMENTS_REVIEW.value,
            ApplicationStatus.DOCUMENTS_REVISION.value,
            ApplicationStatus.READY_FOR_CLIENT.value,
            ApplicationStatus.COMPLETED.value,
            ApplicationStatus.DISPUTE.value,
        }
    )
    assert DocumentFileKind.OWNER_CONSENT.value in document_kinds
    assert DocumentFileKind.CONTRACT.value in document_kinds
    assert event_audiences == {
        NotificationAudience.ADMIN.value,
        NotificationAudience.OWNER.value,
        NotificationAudience.CLIENT.value,
    }
    assert {document["application_code"] for document in payload["documents"]}.issubset(application_codes)
    assert {event["application_code"] for event in payload["events"]}.issubset(application_codes)
