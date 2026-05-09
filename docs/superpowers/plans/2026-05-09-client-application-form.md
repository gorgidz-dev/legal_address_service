# Client Application Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the public client application form that creates a client account and marketplace application in one submission.

**Architecture:** Extend the public marketplace API with `POST /marketplace/applications`. The endpoint accepts a published address, client contact details, password, and application type; it creates a `client` user, creates the application in `admin_review`, and issues the normal session cookie. The public catalog opens an inline application panel from each address card and keeps the existing login flow available.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, React/Vite TypeScript, existing cookie sessions, existing CSS and lucide-react icons.

---

## File Structure

- Modify `app/schemas/marketplace.py`: public client application payload/result schemas.
- Create `app/services/auth_sessions.py`: shared cookie session creation used by auth and marketplace.
- Modify `app/routers/auth.py`: use shared session helper.
- Modify `app/routers/marketplace.py`: public application create endpoint.
- Modify `app/main.py`: mark the public application endpoint as unauthenticated.
- Create `tests/test_marketplace_client_application.py`: public path, schema, endpoint behavior.
- Modify `frontend/src/types.ts`: public application payload/result types.
- Modify `frontend/src/api.ts`: `createPublicApplication`.
- Modify `frontend/src/publicCatalog.tsx`: application form panel and success state.
- Modify `frontend/src/styles.css`: panel/form styles and responsive behavior.

## Task 1: Backend Public Client Application

- [ ] Write failing tests for `/marketplace/applications` public access and initial-registration submission.
- [ ] Add marketplace schemas for public initial registration and address change.
- [ ] Extract shared auth session creation into `app/services/auth_sessions.py`.
- [ ] Add marketplace endpoint that creates a client user, creates an application with `admin_review`, commits, refreshes, and sets a session cookie.
- [ ] Run targeted and full backend tests.

## Task 2: Frontend Application Form

- [ ] Add frontend types and API method.
- [ ] Add address-card form panel with registration/address-change tabs.
- [ ] On successful submit, show account/application created state and allow entering the cabinet.
- [ ] Run frontend build.

## Task 3: Verification And Git Version

- [ ] Run full backend tests.
- [ ] Run frontend build.
- [ ] Smoke-check the public form in the browser.
- [ ] Commit as `feat: add public client application form`.
- [ ] Merge the stage back to `main` after verification.

## Self-Review

- Spec coverage: implements the requested client application form and the approved rule that a client account is created during application submission.
- Scope: does not implement the full client cabinet yet; that is the next module.
- Manual checks: public form, auth redirect/session, and duplicate-email behavior must be verified before commit.
