from __future__ import annotations

from enum import Enum


class ApplicationType(str, Enum):
    INITIAL_REGISTRATION = "initial_registration"
    ADDRESS_CHANGE = "address_change"


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    GUARANTEE_ISSUED = "guarantee_issued"
    AWAITING_CONTRACT = "awaiting_contract"
    CONTRACT_SIGNED = "contract_signed"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    ADMIN_REVIEW = "admin_review"
    NEEDS_CLIENT_FIX = "needs_client_fix"
    ASSIGNED_TO_OWNER = "assigned_to_owner"
    ACCEPTED_BY_OWNER = "accepted_by_owner"
    REJECTED_BY_OWNER = "rejected_by_owner"
    DOCUMENTS_PREPARING = "documents_preparing"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    DOCUMENTS_REVIEW = "documents_review"
    DOCUMENTS_REVISION = "documents_revision"
    READY_FOR_CLIENT = "ready_for_client"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTE = "dispute"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"


class NoticePeriod(str, Enum):
    ONE_DAY = "1d"
    SEVEN_DAYS = "7d"
    ONE_MONTH = "1m"


class GuaranteeVariant(str, Enum):
    INITIAL = "initial"
    FULL = "full"


class TemplateKind(str, Enum):
    CONTRACT = "contract"
    GUARANTEE_INITIAL = "guarantee_initial"
    GUARANTEE_FULL = "guarantee_full"


class GeneratedDocumentKind(str, Enum):
    CONTRACT = "contract"
    GUARANTEE = "guarantee"
    PACKAGE_ZIP = "package_zip"


class UserRole(str, Enum):
    MANAGER = "manager"
    LAWYER = "lawyer"
    ADMIN = "admin"
    CLIENT = "client"
    OWNER = "owner"


class AddressPublicationStatus(str, Enum):
    DRAFT = "draft"
    MODERATION = "moderation"
    PUBLISHED = "published"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class OwnerConnectionRequestStatus(str, Enum):
    NEW = "new"
    REVIEWING = "reviewing"
    INVITED = "invited"
    REJECTED = "rejected"


class ReviewStatus(str, Enum):
    """Статус модерации отзыва об адресе.

    pending   — создан клиентом, ждёт проверки админом (по умолчанию).
    published — одобрен, виден публично и учитывается в среднем рейтинге.
    rejected  — отклонён, не виден, в рейтинг не входит.
    """

    PENDING = "pending"
    PUBLISHED = "published"
    REJECTED = "rejected"


class DocumentFileKind(str, Enum):
    CLIENT_REQUISITES = "client_requisites"
    COMPANY_DETAILS = "company_details"
    OWNERSHIP_PROOF = "ownership_proof"
    GUARANTEE_LETTER = "guarantee_letter"
    CONTRACT = "contract"
    ACT = "act"
    OWNER_CONSENT = "owner_consent"
    POSTAL_SERVICE = "postal_service"
    ADMIN_REVIEW_FILE = "admin_review_file"
    INVOICE = "invoice"  # счёт на оплату для юр.лица — owner-uploaded


class ApplicationEventKind(str, Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    COMMENT_ADDED = "comment_added"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_APPROVED = "document_approved"
    CORRECTION_REQUESTED = "correction_requested"
    DISPUTE_OPENED = "dispute_opened"
    CANCELLED = "cancelled"
    CONTRACT_EXPIRING = "contract_expiring"


class NotificationAudience(str, Enum):
    CLIENT = "client"
    OWNER = "owner"
    ADMIN = "admin"


class EgrulStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LIQUIDATING = "LIQUIDATING"
    LIQUIDATED = "LIQUIDATED"
    BANKRUPT = "BANKRUPT"
    REORGANIZING = "REORGANIZING"


class AddressPhotoModerationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AddressServiceKind(str, Enum):
    """Доп.услуги, доступные на адресе. Цену устанавливает собственник.

    Каталог фиксированный (две группы):
    - юридические документы: guarantee_letter, lease_agreement, owner_confirmation;
    - физический сервис: door_sign, mail_reception, fns_visit_photo,
      phone_answering, visitor_reception.
    """
    GUARANTEE_LETTER = "guarantee_letter"
    LEASE_AGREEMENT = "lease_agreement"
    OWNER_CONFIRMATION = "owner_confirmation"
    DOOR_SIGN = "door_sign"
    MAIL_RECEPTION = "mail_reception"
    FNS_VISIT_PHOTO = "fns_visit_photo"
    PHONE_ANSWERING = "phone_answering"
    VISITOR_RECEPTION = "visitor_reception"


ADDRESS_SERVICE_KIND_VALUES: tuple[str, ...] = tuple(k.value for k in AddressServiceKind)


class PaymentProvider(str, Enum):
    CDEK_PAY = "cdek_pay"
    MANUAL_INVOICE = "manual_invoice"  # юр.лица: счёт от собственника или маркетплейса


class PaymentPayerType(str, Enum):
    INDIVIDUAL = "individual"
    JURIDICAL = "juridical"


class PaymentStatus(str, Enum):
    PENDING = "pending"              # row created, provider not yet called
    AWAITING_USER = "awaiting_user"  # QR/link issued, waiting for payer
    SUCCEEDED = "succeeded"          # provider confirmed payment
    FAILED = "failed"                # provider returned failure / final non-paid
    EXPIRED = "expired"              # QR/link TTL elapsed
    CANCELLED = "cancelled"          # admin blocked the order
    REFUND_REQUESTED = "refund_requested"
    REFUNDED = "refunded"
