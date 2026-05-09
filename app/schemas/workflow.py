from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.enums import ApplicationStatus


class ApplicationActionResult(BaseModel):
    application_id: UUID
    status: ApplicationStatus
    available_actions: list[str]
