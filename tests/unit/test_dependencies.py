from fastapi import HTTPException, status
import pytest

from app.core.dependencies import require_roles
from app.models.user import User, UserRole


def _build_user(role: UserRole) -> User:
    return User(
        id=1,
        employee_id="emp-001",
        name="테스터",
        role=role,
        password_hash="pbkdf2:sha256:...",
    )


@pytest.mark.asyncio
async def test_require_roles_allows_user_with_allowed_role() -> None:
    dependency = require_roles(UserRole.REVIEWER, UserRole.ADMIN)
    user = _build_user(UserRole.REVIEWER)

    result = await dependency(current_user=user)

    assert result is user


@pytest.mark.asyncio
async def test_require_roles_rejects_user_with_unallowed_role() -> None:
    dependency = require_roles(UserRole.ADMIN)
    user = _build_user(UserRole.CONSULTANT)

    with pytest.raises(HTTPException) as exc_info:
        await dependency(current_user=user)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
