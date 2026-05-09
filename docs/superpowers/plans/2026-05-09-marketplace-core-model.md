# Marketplace Core Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first marketplace foundation: real client/owner roles, provider-linked users, marketplace application statuses, owner connection requests, address moderation fields, application notification events, and repeatable demo seed data.

**Architecture:** Keep the existing FastAPI + SQLAlchemy + Alembic structure. Extend current models instead of replacing them: `User.provider_id` links owner users to `Provider`, `Application.created_by` remains the client/user owner of a request, `Address` gets publication moderation fields, and new lightweight tables handle owner onboarding requests and application events. Existing document-generation statuses remain accepted during the transition so current endpoints do not break while later tasks move the UI to marketplace states.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, Pydantic v2, PostgreSQL, pytest, React/Vite TypeScript for type alignment only in this stage.

---

## File Structure

- Modify `app/enums.py`: add `client` and `owner` roles; add marketplace application statuses while preserving legacy statuses; add address moderation, owner request, document kind, and notification event enums.
- Modify `app/models/user.py`: allow new roles and add nullable `provider_id` for owner users.
- Modify `app/models/address.py`: add `publication_status`, `published_at`, `moderation_comment`, `moderated_by`, and `moderated_at`.
- Create `app/models/provider_connection_request.py`: public owner onboarding request table.
- Create `app/models/application_event.py`: internal notification/event journal tied to applications.
- Modify `app/models/__init__.py`: import/export the two new models.
- Modify `app/schemas/auth.py`: allow invitations for `owner` users and expose `provider_id`.
- Create `app/schemas/marketplace.py`: read/create schemas for owner connection requests and application events.
- Create `app/services/marketplace_status.py`: pure helpers for marketplace status labels and valid role actions.
- Create `app/services/notification_events.py`: small service to create application events consistently.
- Create `app/services/marketplace_seed.py`: repeatable seed helper for demo users, providers, addresses, and example marketplace states.
- Create `scripts/seed_marketplace_demo.py`: executable script that calls the seed service.
- Create `alembic/versions/2026_05_09_0000_0004_marketplace_core.py`: schema migration for all model changes.
- Create `tests/test_marketplace_enums.py`: enum and status helper tests.
- Create `tests/test_marketplace_models.py`: SQLAlchemy metadata tests for new columns and tables.
- Create `tests/test_marketplace_schemas.py`: Pydantic schema tests.
- Create `tests/test_notification_events.py`: pure unit tests around event visibility/payload behavior.
- Modify `frontend/src/types.ts`: add client/owner roles and marketplace status union so later frontend work has correct types.

---

## Task 1: Marketplace Enums And Status Helpers

**Files:**
- Modify: `app/enums.py`
- Create: `app/services/marketplace_status.py`
- Create: `tests/test_marketplace_enums.py`
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Write failing enum and status-helper tests**

Create `tests/test_marketplace_enums.py`:

```python
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
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
pytest tests/test_marketplace_enums.py -v
```

Expected: FAIL because `AddressPublicationStatus`, `OwnerConnectionRequestStatus`, `DocumentFileKind`, `ApplicationEventKind`, new `ApplicationStatus` values, and `app.services.marketplace_status` do not exist yet.

- [ ] **Step 3: Extend `app/enums.py`**

Replace the current enum definitions in `app/enums.py` with the following complete content:

```python
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


class ApplicationEventKind(str, Enum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    COMMENT_ADDED = "comment_added"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_APPROVED = "document_approved"
    CORRECTION_REQUESTED = "correction_requested"
    DISPUTE_OPENED = "dispute_opened"
    CANCELLED = "cancelled"


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
```

- [ ] **Step 4: Add pure status helpers**

Create `app/services/marketplace_status.py`:

```python
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
    (UserRole.ADMIN, ApplicationStatus.DISPUTE): ["resolve_dispute", "cancel", "complete"],
    (UserRole.OWNER, ApplicationStatus.ASSIGNED_TO_OWNER): ["accept", "reject"],
    (UserRole.OWNER, ApplicationStatus.ACCEPTED_BY_OWNER): ["start_documents"],
    (UserRole.OWNER, ApplicationStatus.DOCUMENTS_PREPARING): ["upload_documents"],
    (UserRole.OWNER, ApplicationStatus.DOCUMENTS_REVISION): ["upload_documents"],
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
```

- [ ] **Step 5: Update frontend role/status types**

In `frontend/src/types.ts`, replace the `ApplicationStatus` and `UserRole` declarations with:

```ts
export type ApplicationStatus =
  | "draft"
  | "guarantee_issued"
  | "awaiting_contract"
  | "contract_signed"
  | "active"
  | "expired"
  | "terminated"
  | "awaiting_payment"
  | "paid"
  | "admin_review"
  | "needs_client_fix"
  | "assigned_to_owner"
  | "accepted_by_owner"
  | "rejected_by_owner"
  | "documents_preparing"
  | "documents_uploaded"
  | "documents_review"
  | "documents_revision"
  | "ready_for_client"
  | "completed"
  | "cancelled"
  | "dispute"
  | "refund_pending"
  | "refunded";
export type UserRole = "manager" | "lawyer" | "admin" | "client" | "owner";
```

- [ ] **Step 6: Run tests for Task 1**

Run:

```bash
pytest tests/test_marketplace_enums.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit Task 1 if it is implemented independently**

Run:

```bash
git add app/enums.py app/services/marketplace_status.py frontend/src/types.ts tests/test_marketplace_enums.py
git commit -m "feat: add marketplace status enums"
```

Expected: commit succeeds. If executing this plan as one combined first stage, delay the commit until Task 7.

---

## Task 2: User Role Link To Providers

**Files:**
- Modify: `app/models/user.py`
- Modify: `app/schemas/auth.py`
- Modify: `app/routers/auth.py`
- Create: `tests/test_marketplace_models.py`
- Create: `alembic/versions/2026_05_09_0000_0004_marketplace_core.py`

- [ ] **Step 1: Write failing metadata and schema tests**

Create `tests/test_marketplace_models.py`:

```python
from __future__ import annotations

from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.provider_connection_request import ProviderConnectionRequest
from app.models.user import User


def _check_constraint_sql(model, name: str) -> str:
    for constraint in model.__table__.constraints:
        if constraint.name == name or constraint.name.endswith(f"_{name}"):
            return str(constraint.sqltext)
    raise AssertionError(f"{name} not found")


def test_user_model_supports_marketplace_roles_and_provider_link() -> None:
    assert "provider_id" in User.__table__.columns
    foreign_key = next(iter(User.__table__.columns.provider_id.foreign_keys))
    assert str(foreign_key.column) == "providers.id"
    assert "'client'" in _check_constraint_sql(User, "role_valid")
    assert "'owner'" in _check_constraint_sql(User, "role_valid")


def test_address_model_has_publication_moderation_columns() -> None:
    for column_name in (
        "publication_status",
        "published_at",
        "moderation_comment",
        "moderated_by",
        "moderated_at",
    ):
        assert column_name in Address.__table__.columns
    assert "'published'" in _check_constraint_sql(Address, "publication_status_valid")


def test_application_status_constraint_accepts_marketplace_statuses() -> None:
    status_constraint = _check_constraint_sql(Application, "status_valid")
    assert "'awaiting_payment'" in status_constraint
    assert "'documents_review'" in status_constraint
    assert "'ready_for_client'" in status_constraint


def test_provider_connection_request_table_shape() -> None:
    columns = ProviderConnectionRequest.__table__.columns
    assert "company_name" in columns
    assert "contact_email" in columns
    assert "status" in columns
    assert "reviewed_by" in columns
    assert "'invited'" in _check_constraint_sql(ProviderConnectionRequest, "status_valid")


def test_application_event_table_shape() -> None:
    columns = ApplicationEvent.__table__.columns
    assert "application_id" in columns
    assert "kind" in columns
    assert "audience" in columns
    assert "is_read" in columns
    assert "'status_changed'" in _check_constraint_sql(ApplicationEvent, "kind_valid")
```

Append these tests to `tests/test_marketplace_schemas.py` after creating that file in Task 4, or create the file now with only auth schema checks:

```python
from __future__ import annotations

from uuid import uuid4

from app.enums import UserRole
from app.schemas.auth import CurrentUserRead, InvitationCreate


def test_invitation_create_accepts_owner_role() -> None:
    payload = InvitationCreate(email="owner@example.ru", full_name="Анна Собственник", role=UserRole.OWNER)

    assert payload.role == UserRole.OWNER


def test_current_user_read_exposes_provider_id() -> None:
    provider_id = uuid4()
    payload = CurrentUserRead(
        id=uuid4(),
        email="owner@example.ru",
        full_name="Анна Собственник",
        role=UserRole.OWNER,
        is_active=True,
        provider_id=provider_id,
    )

    assert payload.provider_id == provider_id
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest tests/test_marketplace_models.py tests/test_marketplace_schemas.py -v
```

Expected: FAIL because new models and columns do not exist.

- [ ] **Step 3: Update `app/models/user.py`**

Replace `app/models/user.py` with:

```python
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
            name="role_valid",
        ),
        Index("ix_users_provider_id", "provider_id"),
    )

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    provider_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
```

- [ ] **Step 4: Update auth schemas**

In `app/schemas/auth.py`, add `provider_id` to `CurrentUserRead`:

```python
class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    provider_id: Optional[UUID] = None
```

No other auth schema changes are needed because `InvitationCreate.role` already uses `UserRole`; once Task 1 adds `UserRole.OWNER`, invitations can accept it.

- [ ] **Step 5: Preserve invitation-created users without provider link**

In `app/routers/auth.py`, keep existing invitation behavior unchanged. Owner invitations create an active owner user with `provider_id=None`; Task 6 admin workflow will attach provider ownership after moderation. Confirm the `User(...)` constructor in `accept_invitation` does not pass `provider_id`.

- [ ] **Step 6: Run targeted schema tests**

Run:

```bash
pytest tests/test_marketplace_schemas.py::test_invitation_create_accepts_owner_role tests/test_marketplace_schemas.py::test_current_user_read_exposes_provider_id -v
```

Expected: PASS.

---

## Task 3: Address Moderation And Marketplace Application Status Constraint

**Files:**
- Modify: `app/models/address.py`
- Modify: `app/models/application.py`
- Continue: `tests/test_marketplace_models.py`
- Continue: `alembic/versions/2026_05_09_0000_0004_marketplace_core.py`

- [ ] **Step 1: Update address model**

Add these imports to `app/models/address.py`:

```python
from datetime import datetime
```

Extend the SQLAlchemy imports:

```python
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, SmallInteger, Text
```

Add a status constraint to `__table_args__`:

```python
        CheckConstraint(
            "publication_status IN ('draft', 'moderation', 'published', 'rejected', 'archived')",
            name="publication_status_valid",
        ),
```

Add these columns after `notes`:

```python
    publication_status: Mapped[str] = mapped_column(
        Text,
        server_default="'draft'",
        nullable=False,
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    moderation_comment: Mapped[Optional[str]] = mapped_column(Text)
    moderated_by: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    moderated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 2: Update application status constraint**

In `app/models/application.py`, replace the `status_valid` check constraint with:

```python
        CheckConstraint(
            "status IN ("
            "'draft', 'guarantee_issued', 'awaiting_contract', 'contract_signed', "
            "'active', 'expired', 'terminated', 'awaiting_payment', 'paid', "
            "'admin_review', 'needs_client_fix', 'assigned_to_owner', "
            "'accepted_by_owner', 'rejected_by_owner', 'documents_preparing', "
            "'documents_uploaded', 'documents_review', 'documents_revision', "
            "'ready_for_client', 'completed', 'cancelled', 'dispute', "
            "'refund_pending', 'refunded')",
            name="status_valid",
        ),
```

- [ ] **Step 3: Run metadata tests for modified models**

Run:

```bash
pytest tests/test_marketplace_models.py::test_address_model_has_publication_moderation_columns tests/test_marketplace_models.py::test_application_status_constraint_accepts_marketplace_statuses -v
```

Expected: PASS.

---

## Task 4: Owner Connection Requests

**Files:**
- Create: `app/models/provider_connection_request.py`
- Create: `app/schemas/marketplace.py`
- Modify: `app/models/__init__.py`
- Continue: `tests/test_marketplace_models.py`
- Continue: `tests/test_marketplace_schemas.py`

- [ ] **Step 1: Add owner request schema tests**

Append to `tests/test_marketplace_schemas.py`:

```python
from app.enums import OwnerConnectionRequestStatus
from app.schemas.marketplace import ProviderConnectionRequestCreate, ProviderConnectionRequestRead
from datetime import datetime, timezone


def test_provider_connection_request_create_normalizes_email() -> None:
    payload = ProviderConnectionRequestCreate(
        company_name="ООО Адресный фонд",
        contact_name="Игорь Петров",
        contact_email="Owner@Example.Ru",
        contact_phone="+7 900 000-00-00",
        city="Москва",
        address_count=4,
        comment="Есть помещения в ЦАО",
    )

    assert payload.contact_email == "Owner@example.ru"
    assert payload.address_count == 4


def test_provider_connection_request_read_shape() -> None:
    payload = ProviderConnectionRequestRead(
        id=uuid4(),
        company_name="ООО Адресный фонд",
        contact_name="Игорь Петров",
        contact_email="owner@example.ru",
        contact_phone="+7 900 000-00-00",
        city="Москва",
        address_count=4,
        comment="Есть помещения в ЦАО",
        status=OwnerConnectionRequestStatus.NEW,
        admin_comment=None,
        reviewed_by=None,
        reviewed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert payload.status == OwnerConnectionRequestStatus.NEW
```

- [ ] **Step 2: Run failing schema tests**

Run:

```bash
pytest tests/test_marketplace_schemas.py::test_provider_connection_request_create_normalizes_email tests/test_marketplace_schemas.py::test_provider_connection_request_read_shape -v
```

Expected: FAIL because `app.schemas.marketplace` does not exist.

- [ ] **Step 3: Create owner request model**

Create `app/models/provider_connection_request.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin


class ProviderConnectionRequest(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "provider_connection_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new', 'reviewing', 'invited', 'rejected')",
            name="status_valid",
        ),
        CheckConstraint("address_count IS NULL OR address_count >= 0", name="address_count_non_negative"),
        Index("ix_provider_connection_requests_status_created", "status", "created_at"),
        Index("ix_provider_connection_requests_contact_email", "contact_email"),
    )

    company_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str] = mapped_column(Text, nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(Text)
    address_count: Mapped[Optional[int]] = mapped_column(Integer)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="'new'", nullable=False)
    admin_comment: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Create marketplace schemas**

Create `app/schemas/marketplace.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.enums import ApplicationEventKind, NotificationAudience, OwnerConnectionRequestStatus


class ProviderConnectionRequestCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=300)
    contact_name: str = Field(min_length=2, max_length=200)
    contact_email: EmailStr
    contact_phone: Optional[str] = Field(default=None, max_length=80)
    city: Optional[str] = Field(default=None, max_length=120)
    address_count: Optional[int] = Field(default=None, ge=0, le=10_000)
    comment: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("contact_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        local, _, domain = value.partition("@")
        return f"{local}@{domain.lower()}"


class ProviderConnectionRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    contact_name: str
    contact_email: EmailStr
    contact_phone: Optional[str]
    city: Optional[str]
    address_count: Optional[int]
    comment: Optional[str]
    status: OwnerConnectionRequestStatus
    admin_comment: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ApplicationEventCreate(BaseModel):
    application_id: UUID
    kind: ApplicationEventKind
    audience: NotificationAudience
    title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=2, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    kind: ApplicationEventKind
    audience: NotificationAudience
    title: str
    message: str
    payload: dict[str, Any]
    is_read: bool
    created_by: Optional[UUID]
    created_at: datetime
    read_at: Optional[datetime]
```

- [ ] **Step 5: Import model in `app/models/__init__.py`**

Add:

```python
from app.models.provider_connection_request import ProviderConnectionRequest
```

and include `"ProviderConnectionRequest"` in `__all__`.

- [ ] **Step 6: Run owner request tests**

Run:

```bash
pytest tests/test_marketplace_models.py::test_provider_connection_request_table_shape tests/test_marketplace_schemas.py::test_provider_connection_request_create_normalizes_email tests/test_marketplace_schemas.py::test_provider_connection_request_read_shape -v
```

Expected: PASS.

---

## Task 5: Application Events And Notification Service

**Files:**
- Create: `app/models/application_event.py`
- Modify: `app/models/__init__.py`
- Continue: `app/schemas/marketplace.py`
- Create: `app/services/notification_events.py`
- Create: `tests/test_notification_events.py`
- Continue: `tests/test_marketplace_models.py`
- Continue: `tests/test_marketplace_schemas.py`

- [ ] **Step 1: Write notification service tests**

Create `tests/test_notification_events.py`:

```python
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.enums import ApplicationEventKind, NotificationAudience
from app.services.notification_events import event_visible_to_role, event_values


def test_event_values_builds_consistent_payload() -> None:
    application_id = uuid4()
    created_by = uuid4()

    values = event_values(
        application_id=application_id,
        kind=ApplicationEventKind.STATUS_CHANGED,
        audience=NotificationAudience.CLIENT,
        title="Статус изменен",
        message="Заявка перешла на проверку",
        payload={"status": "admin_review"},
        created_by=created_by,
    )

    assert values["application_id"] == application_id
    assert values["kind"] == "status_changed"
    assert values["audience"] == "client"
    assert values["payload"] == {"status": "admin_review"}
    assert values["created_by"] == created_by


def test_event_visibility_matches_audience_and_admin_roles() -> None:
    client_event = SimpleNamespace(audience="client")
    owner_event = SimpleNamespace(audience="owner")
    admin_event = SimpleNamespace(audience="admin")

    assert event_visible_to_role(client_event, "client")
    assert not event_visible_to_role(client_event, "owner")
    assert event_visible_to_role(owner_event, "owner")
    assert event_visible_to_role(admin_event, "admin")
    assert event_visible_to_role(admin_event, "manager")
    assert event_visible_to_role(admin_event, "lawyer")
```

- [ ] **Step 2: Run failing notification tests**

Run:

```bash
pytest tests/test_notification_events.py -v
```

Expected: FAIL because `app.services.notification_events` does not exist.

- [ ] **Step 3: Create application event model**

Create `app/models/application_event.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin


class ApplicationEvent(UUIDPKMixin, Base):
    __tablename__ = "application_events"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('created', 'status_changed', 'comment_added', 'document_uploaded', "
            "'document_approved', 'correction_requested', 'dispute_opened', 'cancelled')",
            name="kind_valid",
        ),
        CheckConstraint("audience IN ('client', 'owner', 'admin')", name="audience_valid"),
        Index("ix_application_events_application_created", "application_id", "created_at"),
        Index("ix_application_events_audience_read", "audience", "is_read", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}", nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 4: Import model in `app/models/__init__.py`**

Add:

```python
from app.models.application_event import ApplicationEvent
```

and include `"ApplicationEvent"` in `__all__`.

- [ ] **Step 5: Create notification service**

Create `app/services/notification_events.py`:

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import utcnow
from app.enums import ApplicationEventKind, NotificationAudience
from app.models.application_event import ApplicationEvent


def event_values(
    *,
    application_id: UUID,
    kind: ApplicationEventKind,
    audience: NotificationAudience,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    return {
        "application_id": application_id,
        "kind": kind.value,
        "audience": audience.value,
        "title": title,
        "message": message,
        "payload": payload or {},
        "created_by": created_by,
        "created_at": utcnow(),
    }


async def create_application_event(
    *,
    db: AsyncSession,
    application_id: UUID,
    kind: ApplicationEventKind,
    audience: NotificationAudience,
    title: str,
    message: str,
    payload: dict[str, Any] | None = None,
    created_by: UUID | None = None,
) -> ApplicationEvent:
    event = ApplicationEvent(
        **event_values(
            application_id=application_id,
            kind=kind,
            audience=audience,
            title=title,
            message=message,
            payload=payload,
            created_by=created_by,
        )
    )
    db.add(event)
    await db.flush()
    return event


def event_visible_to_role(event: object, role: str) -> bool:
    audience = getattr(event, "audience")
    if audience == "admin":
        return role in {"admin", "manager", "lawyer"}
    return audience == role
```

- [ ] **Step 6: Run event tests**

Run:

```bash
pytest tests/test_notification_events.py tests/test_marketplace_models.py::test_application_event_table_shape -v
```

Expected: PASS.

---

## Task 6: Alembic Migration For Marketplace Core

**Files:**
- Create/complete: `alembic/versions/2026_05_09_0000_0004_marketplace_core.py`

- [ ] **Step 1: Create migration file**

Create `alembic/versions/2026_05_09_0000_0004_marketplace_core.py`:

```python
"""marketplace core roles, moderation and events

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _ts_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


APPLICATION_STATUSES = (
    "'draft', 'guarantee_issued', 'awaiting_contract', 'contract_signed', "
    "'active', 'expired', 'terminated', 'awaiting_payment', 'paid', "
    "'admin_review', 'needs_client_fix', 'assigned_to_owner', "
    "'accepted_by_owner', 'rejected_by_owner', 'documents_preparing', "
    "'documents_uploaded', 'documents_review', 'documents_revision', "
    "'ready_for_client', 'completed', 'cancelled', 'dispute', "
    "'refund_pending', 'refunded'"
)


def upgrade() -> None:
    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.add_column("users", sa.Column("provider_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        op.f("fk_users_provider_id_providers"),
        "users",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_provider_id", "users", ["provider_id"])
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
    )

    op.drop_constraint("ck_invitations_role_valid", "invitations", type_="check")
    op.create_check_constraint(
        op.f("ck_invitations_role_valid"),
        "invitations",
        "role IN ('manager', 'lawyer', 'admin', 'client', 'owner')",
    )

    op.add_column(
        "addresses",
        sa.Column("publication_status", sa.Text(), server_default=sa.text("'draft'"), nullable=False),
    )
    op.add_column("addresses", sa.Column("published_at", sa.TIMESTAMP(timezone=True)))
    op.add_column("addresses", sa.Column("moderation_comment", sa.Text()))
    op.add_column("addresses", sa.Column("moderated_by", postgresql.UUID(as_uuid=True)))
    op.add_column("addresses", sa.Column("moderated_at", sa.TIMESTAMP(timezone=True)))
    op.create_foreign_key(
        op.f("fk_addresses_moderated_by_users"),
        "addresses",
        "users",
        ["moderated_by"],
        ["id"],
    )
    op.create_check_constraint(
        op.f("ck_addresses_publication_status_valid"),
        "addresses",
        "publication_status IN ('draft', 'moderation', 'published', 'rejected', 'archived')",
    )

    op.drop_constraint("ck_applications_status_valid", "applications", type_="check")
    op.create_check_constraint(
        op.f("ck_applications_status_valid"),
        "applications",
        f"status IN ({APPLICATION_STATUSES})",
    )

    op.create_table(
        "provider_connection_requests",
        _uuid_pk(),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.Text(), nullable=False),
        sa.Column("contact_email", sa.Text(), nullable=False),
        sa.Column("contact_phone", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("address_count", sa.Integer()),
        sa.Column("comment", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'new'"), nullable=False),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True)),
        *_ts_columns(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_connection_requests")),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], name=op.f("fk_provider_connection_requests_reviewed_by_users")),
        sa.CheckConstraint("status IN ('new', 'reviewing', 'invited', 'rejected')", name=op.f("ck_provider_connection_requests_status_valid")),
        sa.CheckConstraint("address_count IS NULL OR address_count >= 0", name=op.f("ck_provider_connection_requests_address_count_non_negative")),
    )
    op.create_index(
        "ix_provider_connection_requests_status_created",
        "provider_connection_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_provider_connection_requests_contact_email",
        "provider_connection_requests",
        ["contact_email"],
    )

    op.create_table(
        "application_events",
        _uuid_pk(),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("audience", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE", name=op.f("fk_application_events_application_id_applications")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_application_events_created_by_users")),
        sa.CheckConstraint(
            "kind IN ('created', 'status_changed', 'comment_added', 'document_uploaded', "
            "'document_approved', 'correction_requested', 'dispute_opened', 'cancelled')",
            name=op.f("ck_application_events_kind_valid"),
        ),
        sa.CheckConstraint("audience IN ('client', 'owner', 'admin')", name=op.f("ck_application_events_audience_valid")),
    )
    op.create_index(
        "ix_application_events_application_created",
        "application_events",
        ["application_id", "created_at"],
    )
    op.create_index(
        "ix_application_events_audience_read",
        "application_events",
        ["audience", "is_read", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_application_events_audience_read", table_name="application_events")
    op.drop_index("ix_application_events_application_created", table_name="application_events")
    op.drop_table("application_events")

    op.drop_index("ix_provider_connection_requests_contact_email", table_name="provider_connection_requests")
    op.drop_index("ix_provider_connection_requests_status_created", table_name="provider_connection_requests")
    op.drop_table("provider_connection_requests")

    op.drop_constraint("ck_applications_status_valid", "applications", type_="check")
    op.create_check_constraint(
        op.f("ck_applications_status_valid"),
        "applications",
        "status IN ('draft', 'guarantee_issued', 'awaiting_contract', "
        "'contract_signed', 'active', 'expired', 'terminated')",
    )

    op.drop_constraint("ck_addresses_publication_status_valid", "addresses", type_="check")
    op.drop_constraint(op.f("fk_addresses_moderated_by_users"), "addresses", type_="foreignkey")
    op.drop_column("addresses", "moderated_at")
    op.drop_column("addresses", "moderated_by")
    op.drop_column("addresses", "moderation_comment")
    op.drop_column("addresses", "published_at")
    op.drop_column("addresses", "publication_status")

    op.drop_constraint("ck_invitations_role_valid", "invitations", type_="check")
    op.create_check_constraint(
        op.f("ck_invitations_role_valid"),
        "invitations",
        "role IN ('manager', 'lawyer', 'admin')",
    )

    op.drop_constraint("ck_users_role_valid", "users", type_="check")
    op.drop_index("ix_users_provider_id", table_name="users")
    op.drop_constraint(op.f("fk_users_provider_id_providers"), "users", type_="foreignkey")
    op.drop_column("users", "provider_id")
    op.create_check_constraint(
        op.f("ck_users_role_valid"),
        "users",
        "role IN ('manager', 'lawyer', 'admin')",
    )
```

- [ ] **Step 2: Run model and migration-adjacent tests**

Run:

```bash
pytest tests/test_marketplace_models.py tests/test_marketplace_schemas.py tests/test_notification_events.py -v
```

Expected: PASS.

---

## Task 7: Repeatable Demo Seed Data

**Files:**
- Create: `app/services/marketplace_seed.py`
- Create: `scripts/seed_marketplace_demo.py`
- Create: `tests/test_marketplace_seed.py`

- [ ] **Step 1: Write pure seed payload tests**

Create `tests/test_marketplace_seed.py`:

```python
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
```

- [ ] **Step 2: Run failing seed tests**

Run:

```bash
pytest tests/test_marketplace_seed.py -v
```

Expected: FAIL because `app.services.marketplace_seed` does not exist.

- [ ] **Step 3: Create pure seed payload helper**

Create `app/services/marketplace_seed.py`:

```python
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
```

- [ ] **Step 4: Create executable seed script stub**

Create `scripts/seed_marketplace_demo.py`:

```python
from __future__ import annotations

import json
from decimal import Decimal

from app.services.marketplace_seed import marketplace_demo_payload


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def main() -> None:
    payload = marketplace_demo_payload()
    print(json.dumps(payload, ensure_ascii=False, indent=2, cls=_Encoder))


if __name__ == "__main__":
    main()
```

This script intentionally prints deterministic demo data in the core stage. A later API/data stage can add DB upserts after the schema and moderation workflows stabilize.

- [ ] **Step 5: Run seed tests**

Run:

```bash
pytest tests/test_marketplace_seed.py -v
python scripts/seed_marketplace_demo.py
```

Expected: pytest PASS; script prints JSON with users, providers, addresses, and applications.

---

## Task 8: Stage Verification And Commit

**Files:**
- All files from Tasks 1-7

- [ ] **Step 1: Run full backend unit tests**

Run:

```bash
pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
git status --short
```

Expected: only intended marketplace core files are modified or added.

- [ ] **Step 4: Commit the first code stage**

Run:

```bash
git add app frontend/src/types.ts tests scripts alembic/versions/2026_05_09_0000_0004_marketplace_core.py
git commit -m "feat: add marketplace core model"
```

Expected: commit succeeds.

- [ ] **Step 5: Record next-stage readiness**

Run:

```bash
git log --oneline -3
git status --short
```

Expected: latest commit is `feat: add marketplace core model`; status is clean.

---

## Self-Review

- Spec coverage: this plan covers the first approved git stage: real roles, owner/provider link, marketplace statuses, address moderation fields, owner connection request model, notification event model, test data seed basis, tests, build, and commit. It does not implement public catalog, application form, dashboards, admin queues, file upload UI, or real notification center; those are intentionally later plans matching the approved stage order.
- Placeholder scan: the plan contains no deferred implementation markers and every code-changing step includes concrete code or exact replacement text.
- Type consistency: `UserRole.OWNER` maps to `"owner"` everywhere; owner onboarding table uses `ProviderConnectionRequest`; notification audience values are `client`, `owner`, `admin`; application statuses match the specification and frontend union.
