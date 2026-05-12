from __future__ import annotations

from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/legal_address"

    dadata_token: str = ""
    dadata_secret: str = ""

    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "legal-address"
    s3_region: str = "ru-central1"
    storage_backend: str = "local"

    session_cookie_name: str = "legal_address_session"
    session_ttl_hours: int = 24 * 14  # legacy fallback
    web_session_ttl_hours: int = 24
    mobile_session_ttl_hours: int = 24 * 7

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
