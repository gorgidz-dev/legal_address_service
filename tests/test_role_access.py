from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import require_staff
from app.enums import UserRole


@pytest.mark.asyncio
async def test_require_staff_allows_backoffice_roles() -> None:
    for role in (UserRole.MANAGER.value, UserRole.LAWYER.value, UserRole.ADMIN.value):
        user = type("UserStub", (), {"role": role})()
        assert await require_staff(user) is user


@pytest.mark.asyncio
async def test_require_staff_rejects_client_and_owner_roles() -> None:
    for role in (UserRole.CLIENT.value, UserRole.OWNER.value):
        user = type("UserStub", (), {"role": role})()
        with pytest.raises(HTTPException) as exc:
            await require_staff(user)
        assert exc.value.status_code == 403
