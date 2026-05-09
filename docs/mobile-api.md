# Mobile API Notes

This service is expected to have native iOS and Android clients in addition to the web interface.

## Authentication

Web clients keep using the existing HttpOnly cookie session.

Native mobile clients should use bearer sessions:

1. `POST /mobile/auth/login`
2. Store `session.access_token` in secure storage:
   - iOS: Keychain
   - Android: Keystore-backed encrypted storage
3. Send protected requests with:

```http
Authorization: Bearer <access_token>
```

The backend accepts the same session table for both cookie and bearer access. If both a cookie and bearer header are present, the cookie wins so the browser behavior stays deterministic.

## Current Mobile-Ready Endpoints

- `POST /mobile/auth/login` returns `user` and `session`.
- Existing protected endpoints, including `/auth/me` and `/client/applications`, accept bearer auth.
- Public endpoints, including `/marketplace/addresses` and `/marketplace/applications`, stay public.

## Future App Work

When native apps are implemented, keep the API contract JSON-first and avoid depending on browser-only flows:

- Use bearer auth for mobile.
- Keep uploads as multipart endpoints.
- Keep application status labels in the app layer, but statuses themselves must remain stable enum values.
- Add push notification device registration as a separate module when notifications become real.
