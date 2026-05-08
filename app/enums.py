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


class EgrulStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LIQUIDATING = "LIQUIDATING"
    LIQUIDATED = "LIQUIDATED"
    BANKRUPT = "BANKRUPT"
    REORGANIZING = "REORGANIZING"
