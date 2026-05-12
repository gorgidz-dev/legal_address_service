from __future__ import annotations

from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_address"

    # SQLAlchemy / asyncpg connection pool.
    # pool_size: persistent connections kept open.
    # max_overflow: extra short-lived connections allowed under burst (released after use).
    # pool_timeout: seconds to wait for a free connection before raising TimeoutError.
    # pool_recycle: drop & reopen connections older than N seconds (avoids stale server-side conns).
    # pool_pre_ping: lightweight SELECT 1 before checkout — detects dropped connections.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    dadata_token: str = ""
    dadata_secret: str = ""
    dadata_circuit_failure_threshold: int = 3
    dadata_circuit_recovery_seconds: float = 30.0

    # HMAC-SHA256 secret shared with the payment provider for inbound webhook verification.
    # Empty disables the endpoint (returns 503 — not configured).
    payment_webhook_secret: str = ""

    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "legal-address"
    s3_region: str = "ru-central1"
    storage_backend: str = "local"

    session_cookie_name: str = "legal_address_session"
    refresh_cookie_name: str = "legal_address_refresh"
    refresh_cookie_path: str = "/auth/refresh"
    session_ttl_hours: int = 24 * 14  # legacy fallback
    # access token lifetime
    web_session_ttl_hours: int = 24
    mobile_session_ttl_hours: int = 24 * 7
    # refresh token lifetime
    web_refresh_ttl_hours: int = 24 * 30
    mobile_refresh_ttl_hours: int = 24 * 90

    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_domain: Optional[str] = None

    invitation_ttl_hours: int = 24 * 7

    egrn_extract_validity_days: int = 30
    initial_application_validity_days: int = 30

    @model_validator(mode="after")
    def _validate_cookie_security(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError(
                "SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true"
            )
        return self


settings = Settings()
