from __future__ import annotations

from app.enums import ApplicationStatus, UserRole


MARKETPLACE_PRIMARY_FLOW: list[ApplicationStatus] = [
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


_STATUS_LABELS: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "Черновик",
    ApplicationStatus.GUARANTEE_ISSUED: "Гарантийка выдана",
    ApplicationStatus.AWAITING_CONTRACT: "Ожидает договор",
    ApplicationStatus.CONTRACT_SIGNED: "Договор подписан",
    ApplicationStatus.ACTIVE: "Активна",
    ApplicationStatus.EXPIRED: "Истекла",
    ApplicationStatus.TERMINATED: "Расторгнута",
    ApplicationStatus.AWAITING_PAYMENT: "Ожидает оплаты",
    ApplicationStatus.PAID: "Оплачена",
    ApplicationStatus.ADMIN_REVIEW: "Проверка администратором",
    ApplicationStatus.NEEDS_CLIENT_FIX: "Нужны правки клиента",
    ApplicationStatus.ASSIGNED_TO_OWNER: "Передана исполнителю",
    ApplicationStatus.ACCEPTED_BY_OWNER: "Принята исполнителем",
    ApplicationStatus.REJECTED_BY_OWNER: "Отклонена исполнителем",
    ApplicationStatus.DOCUMENTS_PREPARING: "Документы готовятся",
    ApplicationStatus.DOCUMENTS_UPLOADED: "Документы загружены",
    ApplicationStatus.DOCUMENTS_REVIEW: "Проверка документов",
    ApplicationStatus.DOCUMENTS_REVISION: "Документы на доработке",
    ApplicationStatus.READY_FOR_CLIENT: "Готово для клиента",
    ApplicationStatus.COMPLETED: "Завершена",
    ApplicationStatus.CANCELLED: "Отменена",
    ApplicationStatus.DISPUTE: "Спор",
    ApplicationStatus.REFUND_PENDING: "Ожидает возврата",
    ApplicationStatus.REFUNDED: "Возврат выполнен",
}


_ROLE_ACTIONS: dict[tuple[UserRole, ApplicationStatus], list[str]] = {
    (UserRole.ADMIN, ApplicationStatus.PAID): ["start_admin_review"],
    (UserRole.ADMIN, ApplicationStatus.ADMIN_REVIEW): ["assign_owner", "request_client_fix", "cancel"],
    (UserRole.ADMIN, ApplicationStatus.DOCUMENTS_REVIEW): [
        "approve_documents",
        "request_document_revision",
    ],
    (UserRole.ADMIN, ApplicationStatus.REJECTED_BY_OWNER): ["assign_owner", "cancel"],
    (UserRole.ADMIN, ApplicationStatus.DISPUTE): ["resolve_dispute", "cancel", "complete"],
    (UserRole.OWNER, ApplicationStatus.ASSIGNED_TO_OWNER): ["accept", "reject"],
    (UserRole.OWNER, ApplicationStatus.ACCEPTED_BY_OWNER): ["start_documents"],
    (UserRole.CLIENT, ApplicationStatus.NEEDS_CLIENT_FIX): ["submit_corrections"],
    (UserRole.CLIENT, ApplicationStatus.READY_FOR_CLIENT): ["download_documents", "confirm_received", "open_dispute"],
}


def marketplace_status_label(status: ApplicationStatus | str) -> str:
    enum_status = status if isinstance(status, ApplicationStatus) else ApplicationStatus(status)
    return _STATUS_LABELS[enum_status]


def role_actions_for_status(role: UserRole | str, status: ApplicationStatus | str) -> list[str]:
    enum_role = role if isinstance(role, UserRole) else UserRole(role)
    enum_status = status if isinstance(status, ApplicationStatus) else ApplicationStatus(status)
    return list(_ROLE_ACTIONS.get((enum_role, enum_status), []))
