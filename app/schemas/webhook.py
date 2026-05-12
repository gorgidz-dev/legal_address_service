from __future__ import annotations

import secrets
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebhookSubscriptionCreate(BaseModel):
    url: HttpUrl
    description: Optional[str] = Field(default=None, max_length=400)
    events: list[str] = Field(min_length=1, max_length=64)
    secret: Optional[str] = Field(default=None, min_length=16, max_length=128)


class WebhookSubscriptionUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    description: Optional[str] = Field(default=None, max_length=400)
    events: Optional[list[str]] = Field(default=None, min_length=1, max_length=64)
    is_active: Optional[bool] = None
    rotate_secret: bool = False


class WebhookSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    description: Optional[str]
    events: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreateResult(WebhookSubscriptionRead):
    # The raw secret is returned ONLY at creation/rotation — not retrievable later.
    secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    event: str
    status: str
    attempts: int
    last_status_code: Optional[int]
    last_error: Optional[str]
    scheduled_for: datetime
    delivered_at: Optional[datetime]
    created_at: datetime


def generate_secret() -> str:
    """48 bytes of randomness, base64url-encoded → 64 chars."""
    return secrets.token_urlsafe(48)
