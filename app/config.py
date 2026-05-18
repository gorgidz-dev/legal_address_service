from __future__ import annotations

from typing import Literal, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # APP_ENV определяет «строгий режим» проверок безопасности.
    # production → запрещаем выкатывать кабинет с дефолтными значениями
    # (cookie без secure, дефолтный VAPID_SUBJECT, открытый webhook без secret и т.п.).
    # staging → те же проверки, но менее строгие (предупреждения через лог).
    # development (default) → без проверок, всё разрешено локально.
    app_env: Literal["development", "staging", "production"] = "development"

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

    # Яндекс.Карты. Geocoder API (HTTP, серверный) — геокодинг адресов в lat/lon.
    # JS API key для фронта задаётся отдельно через VITE_YANDEX_MAPS_KEY.
    # Пустой ключ → геокодинг выключен (адрес создаётся без координат).
    yandex_geocoder_key: str = ""
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

    # CDEK Pay (SBP for individuals). Empty CDEK_LOGIN / CDEK_SECRET_KEY ⇒
    # the integration is disabled; calls to it return 503.
    cdek_login: str = ""
    cdek_secret_key: str = ""
    cdek_base_url: str = "https://secure.cdekfin.ru"
    cdek_currency: Literal["TST", "RUR"] = "TST"
    cdek_qr_life_time_minutes: int = 10
    cdek_return_success_url: str = ""
    cdek_return_fail_url: str = ""
    cdek_request_timeout_seconds: float = 15.0
    cdek_circuit_failure_threshold: int = 3
    cdek_circuit_recovery_seconds: float = 30.0

    # Web Push (VAPID). Если ключи пустые — push выключен (subscribe возвращает
    # 503, существующие подписки игнорируются при попытке отправки).
    # Сгенерировать новые: см. scripts/gen_vapid_keys.py.
    vapid_public_key: str = ""
    vapid_private_pem: str = ""
    vapid_subject: str = "mailto:noreply@uradres.example"

    @model_validator(mode="after")
    def _validate_cookie_security(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError(
                "SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true"
            )
        return self

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> "Settings":
        """В app_env=production не даём стартовать с небезопасными дефолтами.

        Список проверок и причина каждой — в docs/security-checklist.md.
        Чтобы временно ослабить — выставляй APP_ENV=staging (warning) или
        APP_ENV=development (без проверок).
        """
        if self.app_env != "production":
            return self

        problems: list[str] = []

        # 1) Куки сессии: production = только secure + lax/strict (никаких 'none').
        if not self.session_cookie_secure:
            problems.append("SESSION_COOKIE_SECURE=true обязателен в production")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            problems.append("SESSION_COOKIE_SAMESITE=none без SECURE=true запрещён")

        # 2) Webhook от платёжки — без секрета любой может слать события.
        if not self.payment_webhook_secret:
            problems.append("PAYMENT_WEBHOOK_SECRET пустой — webhook не подписан")

        # 3) DaData креды — без них регистрация контрагента не отработает,
        #    но в production это явный показатель забытого .env.
        if not (self.dadata_token and self.dadata_secret):
            problems.append("DADATA_TOKEN / DADATA_SECRET пустые в production")

        # 4) Storage backend: local небезопасно расшариваем за NGINX'ом — обычно
        #    нужен S3 в проде.
        if self.storage_backend == "local":
            problems.append(
                "STORAGE_BACKEND=local в production: лучше s3 (см. checklist)"
            )

        # 5) VAPID-subject должен указывать на реальный почтовый ящик.
        if self.vapid_subject.endswith("@uradres.example"):
            problems.append("VAPID_SUBJECT остался дефолтным mailto: example")

        # 6) Сессия БД не должна писать SQL в stdout.
        if self.db_echo:
            problems.append("DB_ECHO=true в production — утечёт SQL в логи")

        if problems:
            raise ValueError(
                "Production hardening failed:\n  - " + "\n  - ".join(problems)
            )
        return self


settings = Settings()
