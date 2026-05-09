from __future__ import annotations

from app.enums import AddressPublicationStatus, ApplicationStatus, UserRole
from app.services.marketplace_seed import marketplace_demo_payload


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
