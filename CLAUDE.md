# Claude Code Project Context

Project: marketplace for legal addresses in Russia.

Current date of handoff: 2026-05-10.
Current branch: `main`.
Current HEAD at handoff start: `6b93375 feat: add admin workflow actions`.

## Product Brief

The product is a marketplace where property owners publish legal addresses and clients buy the right to use an address for company registration or address change. The service must support web now and native iOS/Android apps later.

Primary roles:

- `client`: selects an address, creates an application, tracks status, downloads documents.
- `owner`: property owner/provider; receives assigned applications, accepts or rejects them, prepares and uploads documents.
- `admin`: marketplace operator; checks owners, moderates addresses, reviews applications/documents, manually moves applications through exceptional states.
- Existing internal roles `manager` and `lawyer` remain for legacy operational flows.

Approved product decisions:

- Hybrid development: each stage must produce a visible product slice and strengthen the data model.
- Real roles and login are used in MVP.
- Client account is created during application submission.
- Owners join through admin invitation, but a public owner connection request must exist.
- Address publishing and document delivery require manual moderation in MVP.
- Payments can be manual or simulated in MVP; escrow/split payments are postponed.

## Current Stack

Backend:

- FastAPI
- SQLAlchemy async
- PostgreSQL via `asyncpg`
- Alembic migrations
- Pydantic v2
- `docxtpl` for DOCX generation
- Local/S3-compatible storage abstraction

Frontend:

- React
- Vite
- TypeScript
- Lucide icons
- CSS in `frontend/src/styles.css`

## Run Commands

Backend from repo root:

```bash
source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev -- --port 5173
```

Tests:

```bash
source .venv/bin/activate
pytest
cd frontend && npm run build
```

Seed demo data:

```bash
source .venv/bin/activate
python -m scripts.seed_marketplace_demo --password demo12345
```

If `http://127.0.0.1:5173/` shows another project, stop the old Vite process and restart the frontend from this repo's `frontend` directory.

## Important Files

- Backend entrypoint: `app/main.py`
- Domain enums: `app/enums.py`
- Auth/session logic: `app/auth.py`, `app/services/auth_sessions.py`, `app/services/auth_security.py`
- Marketplace public API: `app/routers/marketplace.py`
- Client dashboard: `app/routers/client_dashboard.py`, `app/schemas/client_dashboard.py`
- Owner dashboard: `app/routers/owner_dashboard.py`, `app/schemas/owner_dashboard.py`
- Admin workflow actions: `app/routers/workflow.py`, `app/services/application_workflow.py`
- Document upload/moderation: `app/routers/application_documents.py`, `app/services/application_documents.py`
- Notification events: `app/services/notification_events.py`, `app/routers/notifications.py`
- Demo data: `app/services/marketplace_seed.py`, `scripts/seed_marketplace_demo.py`
- Frontend app shell: `frontend/src/App.tsx`
- Public catalog: `frontend/src/publicCatalog.tsx`
- Frontend API client: `frontend/src/api.ts`
- Shared frontend types: `frontend/src/types.ts`
- Mobile notes: `docs/mobile-api.md`
- Full handoff with diagrams: `docs/handoff/2026-05-10-claude-code-context.md`

## Application Statuses

Main marketplace chain:

`draft` -> `awaiting_payment` -> `paid` -> `admin_review` -> `assigned_to_owner` -> `accepted_by_owner` -> `documents_preparing` -> `documents_uploaded` -> `documents_review` -> `ready_for_client` -> `completed`

Side statuses:

- `needs_client_fix`
- `documents_revision`
- `rejected_by_owner`
- `cancelled`
- `dispute`
- `refund_pending`
- `refunded`

Legacy statuses still exist and must not be broken:

- `guarantee_issued`
- `awaiting_contract`
- `contract_signed`
- `active`
- `expired`
- `terminated`

## Development Rules

- Preserve existing behavior unless the current task explicitly changes it.
- Keep backend enum values stable because future mobile clients will depend on them.
- Keep mobile-facing API JSON-first; uploads should stay multipart.
- Use role-aware action availability from the backend rather than duplicating workflow authority in the frontend.
- Add or update tests for backend behavior changes.
- Every meaningful stage should be saved as a git commit.
- Do not commit `.env`, virtual environments, `node_modules`, generated build output, or local caches.

## What Is Done

- Public address catalog.
- Client application form with account creation during application submission.
- Client dashboard.
- Mobile bearer-session readiness.
- Owner dashboard.
- Marketplace application statuses.
- Owner document upload.
- Admin document moderation.
- Demo marketplace seed data.
- Notification inbox.
- Admin workflow actions.

## Next Recommended Work

Start with the provider onboarding/admin invitation slice:

1. Admin queue for public owner connection requests.
2. Admin action to invite an owner from an approved request.
3. Owner invitation acceptance path validation.
4. UI state for request statuses `new`, `reviewing`, `invited`, `rejected`.
5. Tests for request review, invitation creation, and role access.

Then continue with address publication moderation, client correction flow, and payment confirmation.
