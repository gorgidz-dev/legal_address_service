# Public Address Catalog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the public marketplace entry point: published address catalog, filters, public owner connection request form, and a frontend public screen available before login.

**Architecture:** Add a dedicated `marketplace` API router for public endpoints and keep internal `/addresses` unchanged. The frontend keeps the existing authenticated workspace, but unauthenticated users now see the catalog first with a compact login panel instead of being forced directly into auth.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, React/Vite TypeScript, existing CSS, existing `lucide-react` icons.

---

## File Structure

- Modify `app/main.py`: include marketplace router and mark public marketplace endpoints as unauthenticated.
- Create `app/routers/marketplace.py`: public address list and owner connection request create endpoints.
- Extend `app/schemas/marketplace.py`: public address card schema.
- Create `tests/test_marketplace_public_api.py`: public path and pure catalog serialization tests.
- Modify `frontend/src/types.ts`: add `PublicAddress` and owner request payload/result types.
- Modify `frontend/src/api.ts`: add `publicAddresses()` and `createProviderConnectionRequest()`.
- Create `frontend/src/publicCatalog.tsx`: public catalog page, filters, login panel, owner request form.
- Modify `frontend/src/App.tsx`: show public catalog when logged out; keep bootstrap/admin login available.
- Modify `frontend/src/styles.css`: catalog layout, address cards, filter bar, owner request form states.

---

## Task 1: Public Marketplace API

**Files:**
- Modify: `app/main.py`
- Create: `app/routers/marketplace.py`
- Modify: `app/schemas/marketplace.py`
- Create: `tests/test_marketplace_public_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_marketplace_public_api.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.main import _is_public_path
from app.routers.marketplace import public_address_from_row


def test_marketplace_public_paths_do_not_require_auth() -> None:
    assert _is_public_path("/marketplace/addresses", "GET")
    assert _is_public_path("/marketplace/provider-requests", "POST")
    assert not _is_public_path("/marketplace/provider-requests", "GET")


def test_public_address_from_row_uses_selected_term_price() -> None:
    address_id = uuid4()
    provider_id = uuid4()
    now = datetime.now(timezone.utc)
    address = SimpleNamespace(
        id=address_id,
        provider_id=provider_id,
        full_address="г. Москва, ул. Тверская, д. 7, офис 41",
        room_number="офис 41",
        price_6m=Decimal("18000.00"),
        price_11m=Decimal("30000.00"),
        correspondence_price=Decimal("3500.00"),
        fns_number=46,
        fns_city="Москве",
        is_available=True,
        publication_status="published",
        created_at=now,
        updated_at=now,
    )
    provider = SimpleNamespace(short_name="Московский адресный фонд")

    payload = public_address_from_row(address=address, provider=provider, term_months=11)

    assert payload.id == address_id
    assert payload.provider_name == "Московский адресный фонд"
    assert payload.selected_price == Decimal("30000.00")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_marketplace_public_api.py -v
```

Expected: FAIL because `app.routers.marketplace` and public path registration do not exist.

- [ ] **Step 3: Add public address schema**

Append to `app/schemas/marketplace.py`:

```python
from decimal import Decimal


class PublicAddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider_id: UUID
    provider_name: str
    full_address: str
    room_number: Optional[str]
    price_6m: Decimal
    price_11m: Decimal
    selected_price: Decimal
    correspondence_price: Optional[Decimal]
    fns_number: Optional[int]
    fns_city: Optional[str]
    is_available: bool
    publication_status: str
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Add marketplace router**

Create `app/routers/marketplace.py`:

```python
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.enums import AddressPublicationStatus, OwnerConnectionRequestStatus
from app.models.address import Address
from app.models.provider import Provider
from app.models.provider_connection_request import ProviderConnectionRequest
from app.schemas.marketplace import (
    ProviderConnectionRequestCreate,
    ProviderConnectionRequestRead,
    PublicAddressRead,
)

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def public_address_from_row(
    *,
    address: Address,
    provider: Provider,
    term_months: Literal[6, 11] = 11,
) -> PublicAddressRead:
    selected_price: Decimal = address.price_6m if term_months == 6 else address.price_11m
    return PublicAddressRead(
        id=address.id,
        provider_id=address.provider_id,
        provider_name=provider.short_name,
        full_address=address.full_address,
        room_number=address.room_number,
        price_6m=address.price_6m,
        price_11m=address.price_11m,
        selected_price=selected_price,
        correspondence_price=address.correspondence_price,
        fns_number=address.fns_number,
        fns_city=address.fns_city,
        is_available=address.is_available,
        publication_status=address.publication_status,
        created_at=address.created_at,
        updated_at=address.updated_at,
    )


@router.get("/addresses", response_model=list[PublicAddressRead])
async def public_addresses(
    city: Optional[str] = Query(default=None, max_length=120),
    fns_number: Optional[int] = Query(default=None, ge=1, le=9999),
    term_months: Literal[6, 11] = 11,
    correspondence: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
) -> list[PublicAddressRead]:
    stmt = (
        select(Address, Provider)
        .join(Provider, Provider.id == Address.provider_id)
        .where(
            Provider.is_active.is_(True),
            Address.is_available.is_(True),
            Address.publication_status == AddressPublicationStatus.PUBLISHED.value,
        )
        .order_by(Address.full_address)
    )
    if city:
        stmt = stmt.where(Address.full_address.ilike(f"%{city.strip()}%"))
    if fns_number is not None:
        stmt = stmt.where(Address.fns_number == fns_number)
    if correspondence is True:
        stmt = stmt.where(Address.correspondence_price.is_not(None))

    result = await db.execute(stmt)
    return [
        public_address_from_row(address=address, provider=provider, term_months=term_months)
        for address, provider in result.all()
    ]


@router.post(
    "/provider-requests",
    response_model=ProviderConnectionRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_request(
    payload: ProviderConnectionRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> ProviderConnectionRequest:
    request = ProviderConnectionRequest(
        **payload.model_dump(),
        status=OwnerConnectionRequestStatus.NEW.value,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)
    return request
```

- [ ] **Step 5: Register router and public paths**

In `app/main.py`, import `marketplace`, include it, and update `_is_public_path`:

```python
from app.routers import (
    addresses,
    applications,
    auth,
    clients,
    egrn,
    marketplace,
    providers,
    registry,
    templates,
)
```

Inside `_is_public_path` add:

```python
    if path == "/marketplace/addresses" and method == "GET":
        return True
    if path == "/marketplace/provider-requests" and method == "POST":
        return True
```

Add:

```python
app.include_router(marketplace.router)
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest tests/test_marketplace_public_api.py -v
PYTHONPATH=. ./.venv/bin/pytest -q
```

Expected: PASS.

---

## Task 2: Frontend API And Types

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Add TypeScript types**

Add to `frontend/src/types.ts`:

```ts
export interface PublicAddress {
  id: string;
  provider_id: string;
  provider_name: string;
  full_address: string;
  room_number: string | null;
  price_6m: string;
  price_11m: string;
  selected_price: string;
  correspondence_price: string | null;
  fns_number: number | null;
  fns_city: string | null;
  is_available: boolean;
  publication_status: string;
  created_at: string;
  updated_at: string;
}

export interface ProviderConnectionRequestCreate {
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone?: string | null;
  city?: string | null;
  address_count?: number | null;
  comment?: string | null;
}

export interface ProviderConnectionRequest {
  id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string | null;
  city: string | null;
  address_count: number | null;
  comment: string | null;
  status: "new" | "reviewing" | "invited" | "rejected";
  admin_comment: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add API methods**

In `frontend/src/api.ts`, import the new types and add:

```ts
  publicAddresses: (filters?: { city?: string; fns_number?: number | ""; term_months?: 6 | 11; correspondence?: boolean }) => {
    const params = new URLSearchParams();
    if (filters?.city) params.set("city", filters.city);
    if (filters?.fns_number) params.set("fns_number", String(filters.fns_number));
    if (filters?.term_months) params.set("term_months", String(filters.term_months));
    if (filters?.correspondence) params.set("correspondence", "true");
    const query = params.toString();
    return request<PublicAddress[]>(`/marketplace/addresses${query ? `?${query}` : ""}`);
  },
  createProviderConnectionRequest: (payload: ProviderConnectionRequestCreate) =>
    request<ProviderConnectionRequest>("/marketplace/provider-requests", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
```

- [ ] **Step 3: Run build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

---

## Task 3: Public Catalog Screen

**Files:**
- Create: `frontend/src/publicCatalog.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Create public catalog component**

Create `frontend/src/publicCatalog.tsx` with a component that:

- fetches `api.publicAddresses()` on mount and when filters change;
- renders filters for city, IФНС, term 6/11, correspondence;
- renders address cards with price, IФНС, provider name, correspondence option;
- has a compact login panel that reuses an `onLoginClick` callback;
- has an owner request form using `api.createProviderConnectionRequest()`;
- shows loading, empty, error, and success states.

- [ ] **Step 2: Wire logged-out app state**

In `frontend/src/App.tsx`, replace the logged-out return:

```tsx
if (!currentUser) {
  return <AuthView canBootstrap={canBootstrap} onAuthenticated={(user) => setCurrentUser(user)} />;
}
```

with a public catalog view that can open the existing auth form.

- [ ] **Step 3: Add catalog styles**

In `frontend/src/styles.css`, add responsive styles for:

- `.public-shell`
- `.public-topbar`
- `.catalog-layout`
- `.catalog-filters`
- `.address-grid`
- `.address-card`
- `.owner-request-panel`
- mobile single-column behavior.

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

---

## Task 4: Final Verification And Commit

**Files:** all files from this plan.

- [ ] **Step 1: Run full verification**

Run:

```bash
PYTHONPATH=. ./.venv/bin/pytest -q
cd frontend && npm run build
```

Expected: backend tests and frontend build PASS.

- [ ] **Step 2: Run browser verification**

Start the app locally and open the public catalog. Confirm:

- logged-out screen is catalog, not forced auth;
- filters render;
- owner request form renders;
- login panel can open auth form.

- [ ] **Step 3: Commit**

Run:

```bash
git add app frontend/src tests
git commit -m "feat: add public address catalog"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: this implements the second approved stage: public catalog, filters, public owner connection request, and logged-out public screen. It intentionally does not create client application submission yet; that is the next stage.
- Placeholder scan: no task contains deferred implementation markers.
- Type consistency: backend `PublicAddressRead` matches frontend `PublicAddress`; owner request API uses the existing marketplace request schema.
