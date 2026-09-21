from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.user import User
from app.enums import ApplicationStatus
from app.schemas.workflow import ApplicationActionResult
from app.services.application_workflow import apply_application_action
from app.services.tbank_receipts import send_due_for_application

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/applications/{application_id}/actions/{action}", response_model=ApplicationActionResult)
async def run_application_action(
    application_id: UUID,
    action: str,
    background: BackgroundTasks,
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
    if result.status == ApplicationStatus.READY_FOR_CLIENT:
        # Закрывающий чек — сразу после коммита, не дожидаясь крона (крон —
        # страховка, если банк не ответил или процесс перезапустился).
        background.add_task(send_due_for_application, application_id)
    return result
