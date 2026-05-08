from __future__ import annotations

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

    egrn_extract_validity_days: int = 30
    initial_application_validity_days: int = 30


settings = Settings()
