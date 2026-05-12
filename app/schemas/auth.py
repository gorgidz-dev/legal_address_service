from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import UserRole


class BootstrapAdminRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class InvitationCreate(BaseModel):
    email: EmailStr
    full_name: Optional[str] = Field(default=None, max_length=200)
    role: UserRole = UserRole.MANAGER


class InvitationAccept(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class CurrentUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    provider_id: Optional[UUID] = None


class AuthResponse(BaseModel):
    user: CurrentUserRead


class SessionTokenRead(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


class MobileAuthResponse(AuthResponse):
    session: SessionTokenRead


class MobileRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=400)


class MobileRefreshResponse(BaseModel):
    session: SessionTokenRead


class BootstrapState(BaseModel):
    can_bootstrap: bool


class SessionRead(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    refresh_expires_at: Optional[datetime] = None
    last_refreshed_at: Optional[datetime] = None
    is_current: bool


class InvitationCreateResult(BaseModel):
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    role: UserRole
    expires_at: datetime
    accepted_at: Optional[datetime]
    invitation_token: str
    invitation_path: str


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: Optional[str]
    role: UserRole
    expires_at: datetime
    accepted_at: Optional[datetime]
    created_at: datetime
    created_by: Optional[UUID]
