from __future__ import annotations

from app.enums import (
    AddressPublicationStatus,
    ApplicationEventKind,
    ApplicationStatus,
    DocumentFileKind,
    OwnerConnectionRequestStatus,
    UserRole,
)
from app.services.marketplace_status import (
    MARKETPLACE_PRIMARY_FLOW,
    marketplace_status_label,
    role_actions_for_status,
)


def test_marketplace_user_roles_are_available() -> None:
    assert UserRole.CLIENT.value == "client"
    assert UserRole.OWNER.value == "owner"


def test_marketplace_application_statuses_preserve_legacy_statuses() -> None:
    assert ApplicationStatus.DRAFT.value == "draft"
    assert ApplicationStatus.GUARANTEE_ISSUED.value == "guarantee_issued"
    assert ApplicationStatus.AWAITING_PAYMENT.value == "awaiting_payment"
    assert ApplicationStatus.ADMIN_REVIEW.value == "admin_review"
    assert ApplicationStatus.READY_FOR_CLIENT.value == "ready_for_client"
    assert ApplicationStatus.REFUNDED.value == "refunded"


def test_marketplace_supporting_enums_are_available() -> None:
    assert AddressPublicationStatus.PUBLISHED.value == "published"
    assert AddressPublicationStatus.MODERATION.value == "moderation"
    assert OwnerConnectionRequestStatus.NEW.value == "new"
    assert OwnerConnectionRequestStatus.INVITED.value == "invited"
    assert DocumentFileKind.OWNER_CONSENT.value == "owner_consent"
    assert ApplicationEventKind.STATUS_CHANGED.value == "status_changed"


def test_marketplace_primary_flow_is_ordered() -> None:
    assert MARKETPLACE_PRIMARY_FLOW == [
        ApplicationStatus.DRAFT,
        ApplicationStatus.AWAITING_PAYMENT,
        ApplicationStatus.PAID,
        ApplicationStatus.ADMIN_REVIEW,
        ApplicationStatus.ASSIGNED_TO_OWNER,
        ApplicationStatus.ACCEPTED_BY_OWNER,
        ApplicationStatus.DOCUMENTS_PREPARING,
        ApplicationStatus.DOCUMENTS_UPLOADED,
        ApplicationStatus.DOCUMENTS_REVIEW,
        ApplicationStatus.READY_FOR_CLIENT,
        ApplicationStatus.COMPLETED,
    ]


def test_status_labels_and_role_actions_are_role_specific() -> None:
    assert marketplace_status_label(ApplicationStatus.ADMIN_REVIEW) == "Проверка администратором"
    assert role_actions_for_status(UserRole.ADMIN, ApplicationStatus.PAID) == ["start_admin_review"]
    assert role_actions_for_status(UserRole.OWNER, ApplicationStatus.ASSIGNED_TO_OWNER) == [
        "accept",
        "reject",
    ]
    assert role_actions_for_status(UserRole.CLIENT, ApplicationStatus.NEEDS_CLIENT_FIX) == [
        "submit_corrections",
    ]
    assert role_actions_for_status(UserRole.MANAGER, ApplicationStatus.READY_FOR_CLIENT) == []
