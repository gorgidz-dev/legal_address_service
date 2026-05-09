# Owner Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an MVP cabinet for the executor / address owner so they can see their organization, addresses, and applications that have reached the owner workflow.

**Architecture:** Add an authenticated `/owner/dashboard` API protected by the `owner` role. The endpoint uses `user.provider_id` as the ownership boundary, returns only that provider's addresses, and returns only applications in owner-visible statuses. The frontend renders a separate owner dashboard for `role=owner` instead of the internal staff navigation.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, React/Vite TypeScript, existing cookie and bearer sessions, existing CSS and lucide-react icons.

---

## File Structure

- Modify `app/auth.py`: add `require_owner`.
- Create `app/schemas/owner_dashboard.py`: provider, address, application, and timeline response models.
- Create `app/routers/owner_dashboard.py`: `/owner/dashboard`.
- Modify `app/main.py`: include owner dashboard router.
- Create `tests/test_owner_dashboard.py`: owner guard, provider binding, ownership filtering, owner-visible statuses, and owner event filtering.
- Modify `frontend/src/types.ts`: owner dashboard types.
- Modify `frontend/src/api.ts`: `ownerDashboard`.
- Modify `frontend/src/App.tsx`: owner dashboard screen and owner route.
- Modify `frontend/src/styles.css`: owner dashboard layout and responsive styles.
- Modify `frontend/vite.config.ts`: proxy `/owner`.

## Task 1: Backend Owner API

- [x] Write failing tests for owner role guard and dashboard filtering.
- [x] Add `require_owner`.
- [x] Add owner dashboard schemas.
- [x] Add `/owner/dashboard` with `provider_id` ownership boundary.
- [x] Filter applications to owner-visible statuses.
- [x] Filter events to `audience=owner`.

## Task 2: Frontend Owner Cabinet

- [x] Add frontend types and API method.
- [x] Route `owner` users to a dedicated dashboard.
- [x] Show provider, address inventory, owner-visible applications, available action names, and owner timeline.
- [x] Keep loading, empty, and error states.

## Task 3: Verification And Git Version

- [x] Run targeted owner dashboard tests.
- [x] Run full backend tests.
- [x] Run frontend build.
- [x] Smoke-check owner login/dashboard in the browser.
- [ ] Commit as `feat: add owner dashboard`.
- [ ] Merge the stage back to `main` after verification.

## Self-Review

- Scope: does not mutate statuses and does not upload documents yet; those remain separate modules.
- Access: owner data is bounded by `user.provider_id`.
- Visibility: applications still under manual admin review are hidden from owners.
