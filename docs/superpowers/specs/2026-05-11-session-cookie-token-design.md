# Session Cookie and Mobile Token Design

Date: 2026-05-11

## Summary

The service already supports two authentication transport modes:

- web clients use an HttpOnly cookie named `legal_address_session`;
- mobile clients use a bearer `access_token` returned by `POST /mobile/auth/login`.

The next step is to make those modes explicit in configuration and session creation without changing the database schema yet. Web and mobile sessions should have separate TTL settings, web cookie attributes should be configurable for production deployment, and mobile login should continue to avoid setting cookies.

This is a compatibility-focused change. Existing session records remain stored in `user_sessions` with a token hash, expiry, creation time, and optional revocation time.

## Goals

- Separate web and mobile session lifetime settings.
- Make web cookie security attributes configurable through environment variables.
- Preserve current cookie and bearer authentication behavior.
- Keep mobile auth JSON-first and compatible with future native apps.
- Avoid a database migration in this slice.
- Cover the behavior with focused backend tests.

## Non-Goals

- Refresh tokens.
- Token rotation.
- Device/session management UI.
- Adding `session_type` to `user_sessions`.
- Changing frontend login flows.
- Changing role authorization rules.

## Current Behavior

`app/services/auth_sessions.py` creates a random URL-safe token, stores only its hash in `user_sessions`, and sets a cookie when a `Response` is provided and `set_cookie=True`.

`app/main.py` authenticates protected requests by first checking the web cookie and then falling back to `Authorization: Bearer <token>`.

`app/routers/mobile_auth.py` calls `create_session(..., set_cookie=False)` and returns the raw token in the `session.access_token` response body.

The current cookie settings are fixed in code:

- `httponly=True`
- `secure=False`
- `samesite="lax"`
- `path="/"`

The current TTL setting is shared:

- `session_ttl_hours = 336`

## Proposed Behavior

Add explicit session profiles:

- `web`: creates a session with the web TTL and sets the HttpOnly cookie.
- `mobile`: creates a session with the mobile TTL and does not set a cookie.

The database record shape stays unchanged. The profile affects session creation behavior only.

Protected request authentication remains unchanged:

1. Prefer `settings.session_cookie_name` from the request cookies.
2. If no cookie is present, accept `Authorization: Bearer <token>`.
3. Check the token hash against active, unexpired, non-revoked sessions.

## Configuration

Add these settings to `app/config.py`:

- `web_session_ttl_hours: int`
- `mobile_session_ttl_hours: int`
- `session_cookie_secure: bool`
- `session_cookie_samesite: Literal["lax", "strict", "none"]` or equivalent validation
- `session_cookie_domain: str | None`

Keep the existing `session_ttl_hours` setting as the legacy web-session fallback. If `web_session_ttl_hours` is not explicitly configured, web sessions should keep the current 14-day lifetime. Mobile sessions get their own default because native clients usually need a longer login window than browser sessions.

Suggested defaults:

- `session_ttl_hours = 336`
- `web_session_ttl_hours = 336`
- `mobile_session_ttl_hours = 720`
- `session_cookie_secure = False`
- `session_cookie_samesite = "lax"`
- `session_cookie_domain = None`

Production `.env` can then set:

```env
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=lax
SESSION_COOKIE_DOMAIN=.example.com
WEB_SESSION_TTL_HOURS=336
MOBILE_SESSION_TTL_HOURS=720
```

If `SESSION_COOKIE_SAMESITE=none`, deployment must also set `SESSION_COOKIE_SECURE=true`; the implementation should reject an unsafe `SameSite=None` cookie configuration at startup or when building cookie parameters.

## Backend API Shape

Keep response schemas stable.

Web endpoints continue to return:

```json
{
  "user": { "...": "..." }
}
```

and set the session cookie.

Mobile login continues to return:

```json
{
  "user": { "...": "..." },
  "session": {
    "access_token": "...",
    "token_type": "bearer",
    "expires_at": "..."
  }
}
```

and must not set the session cookie.

## Implementation Boundaries

Primary files:

- `app/config.py`
- `app/services/auth_sessions.py`
- `app/routers/auth.py`
- `app/routers/mobile_auth.py`
- `tests/test_mobile_api_auth.py`
- `tests/test_marketplace_client_application.py` or a focused new auth-session test file
- `.env.example`

No frontend code is required for this slice.

## Error Handling

- Invalid login credentials remain `401`.
- Expired or revoked sessions remain `401`.
- Unsafe cookie config should fail fast with a clear error rather than silently sending an insecure cross-site cookie.
- Logout should delete the web cookie with the same `path` and configured `domain` used when setting it.

## Testing Plan

Use test-first implementation.

Add focused backend tests for:

- web session creation sets a cookie and uses `web_session_ttl_hours`;
- mobile login returns a bearer token, sets no cookie, and uses `mobile_session_ttl_hours`;
- cookie authentication remains preferred over bearer authentication when both are present;
- logout deletes the cookie with the configured path/domain;
- `SameSite=None` with `secure=False` is rejected.

Existing tests for password hashing, token hashing, role access, mobile login, and marketplace application session creation should continue to pass.

## Future Work

A later slice can add a `session_type` column and optional device metadata:

- `session_type`: `web` or `mobile`;
- `user_agent`;
- `ip_address`;
- `device_name`;
- `last_seen_at`;
- per-session revoke endpoints;
- refresh token rotation for mobile apps.

That later migration should be separate because it changes persistence semantics and admin/client UX.
