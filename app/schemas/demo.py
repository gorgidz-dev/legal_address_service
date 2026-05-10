from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import UserRole


class DemoCredential(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole
    password: str


class DemoSeedCounts(BaseModel):
    users: int = 0
    providers: int = 0
    clients: int = 0
    addresses: int = 0
    applications: int = 0
    documents: int = 0
    events: int = 0


class DemoSeedRequest(BaseModel):
    password: str = Field(default="demo12345", min_length=8, max_length=200)


class DemoSeedResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    created: DemoSeedCounts
    updated: DemoSeedCounts
    credentials: list[DemoCredential]
