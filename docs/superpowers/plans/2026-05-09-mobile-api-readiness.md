# Mobile API Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the backend contract for future iOS and Android apps without changing the existing browser login flow.

**Architecture:** Keep browser sessions on the existing HttpOnly cookie. Add a mobile auth namespace that returns the raw session token as a bearer token, and teach the auth middleware to accept either the browser cookie or `Authorization: Bearer <token>`. Both mechanisms use the same `user_sessions` table and expiry/revocation rules.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, existing user session model.

---

## File Structure

- Modify `app/services/auth_sessions.py`: return generated session credentials and allow cookie-less session creation.
- Modify `app/schemas/auth.py`: add mobile bearer session response schema.
- Create `app/routers/mobile_auth.py`: mobile login endpoint.
- Modify `app/main.py`: accept bearer tokens in middleware and include mobile router.
- Modify `app/routers/auth.py`: restore required imports for web auth endpoints.
- Create `tests/test_mobile_api_auth.py`: mobile login and bearer token extraction tests.
- Create `docs/mobile-api.md`: notes for future iOS/Android app implementation.

## Task 1: Mobile Auth Contract

- [x] Write failing tests for mobile login and bearer token extraction.
- [x] Add cookie-less session credential creation.
- [x] Add mobile login response with `session.access_token`.
- [x] Add `/mobile/auth/login`.

## Task 2: Middleware Compatibility

- [x] Add request token extraction with cookie-first, bearer-second priority.
- [x] Keep protected endpoints compatible with browser cookie sessions.
- [x] Mark `/mobile/auth/login` as public.

## Task 3: Verification And Git Version

- [x] Run targeted mobile auth tests.
- [x] Run full backend tests.
- [x] Run frontend build.
- [ ] Commit as `feat: prepare mobile api auth`.
- [ ] Merge the stage back to `main` after verification.

## Self-Review

- Scope: does not start iOS/Android apps yet; only prepares the server API contract they need.
- Security: token is returned only from the mobile namespace; browser auth responses remain cookie-based.
- Compatibility: existing web session cookies continue to work.
