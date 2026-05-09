# Client Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the client placeholder with a real MVP cabinet where a client sees only their own applications, selected address, price, status, and client-visible event timeline.

**Architecture:** Add an authenticated `/client/applications` API protected by the `client` role. The endpoint joins the client-owned application with its address and provider, calculates the selected term price, and returns only client-audience events. The public application flow creates the first client event so a new account immediately has a timeline entry.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, React/Vite TypeScript, existing cookie sessions, existing CSS and lucide-react icons.

---

## File Structure

- Modify `app/auth.py`: add `require_client`.
- Create `app/schemas/client_dashboard.py`: client application read model with events.
- Create `app/routers/client_dashboard.py`: `/client/applications`.
- Modify `app/routers/marketplace.py`: create the first client-visible event for public applications.
- Modify `app/main.py`: include the client dashboard router.
- Create `tests/test_client_dashboard.py`: role guard and client application payload behavior.
- Modify `tests/test_marketplace_client_application.py`: assert public application creates a client event.
- Modify `frontend/src/types.ts`: client dashboard types.
- Modify `frontend/src/api.ts`: `clientApplications`.
- Modify `frontend/src/App.tsx`: client dashboard screen.
- Modify `frontend/src/styles.css`: client dashboard layout and responsive styles.
- Modify `frontend/vite.config.ts`: proxy `/client`.

## Task 1: Backend Client API

- [x] Write failing tests for `require_client` and the owned application timeline.
- [x] Add client-only role guard.
- [x] Add client dashboard response schema.
- [x] Add `/client/applications` with ownership and event filtering.
- [x] Create a first client event during public application creation.

## Task 2: Frontend Client Cabinet

- [x] Add dashboard types and API method.
- [x] Replace the client placeholder with a real dashboard.
- [x] Show application list, status, selected price, address/provider details, and event timeline.
- [x] Add loading, empty, and error states.

## Task 3: Verification And Git Version

- [x] Run full backend tests.
- [x] Run frontend build.
- [x] Smoke-check the public application flow and client dashboard in the browser.
- [ ] Commit as `feat: add client dashboard`.
- [ ] Merge the stage back to `main` after verification.

## Self-Review

- Scope: implements the client cabinet MVP only; document upload remains a separate module.
- Access: client endpoint is not public and filters both applications and events to the current client context.
- UI: keeps the operational dashboard style, with no staff data loading for client users.
