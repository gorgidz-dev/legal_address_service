from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.workflow import ApplicationActionResult
from app.services.application_workflow import apply_application_action

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/applications/{application_id}/actions/{action}", response_model=ApplicationActionResult)
async def run_application_action(
    application_id: UUID,
    action: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationActionResult:
    result = await apply_application_action(
        db=db,
        application_id=application_id,
        action=action,
        user=user,
    )
    await db.commit()
    return result
