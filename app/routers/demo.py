from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.demo import DemoSeedRequest, DemoSeedResult
from app.services.marketplace_seed import seed_marketplace_demo

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", response_model=DemoSeedResult)
async def seed_demo_data(
    payload: DemoSeedRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> DemoSeedResult:
    result = await seed_marketplace_demo(db=db, password=payload.password)
    await db.commit()
    return result
