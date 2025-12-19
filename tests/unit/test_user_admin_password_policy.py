import pytest

from app.core.exceptions import ValidationError
from app.services.user_admin_service import UserAdminService


class DummyRepo:
    pass


class DummyDepartmentService:
    pass


@pytest.fixture
def admin_service():
    return UserAdminService(
        session=None,  # only testing password policy
        user_repo=DummyRepo(),
        department_service=DummyDepartmentService(),
    )


@pytest.mark.asyncio
async def test_password_policy_accepts_valid_password(admin_service):
    await admin_service._enforce_password_policy("Strong!Passphrase1")


@pytest.mark.parametrize(
    "password",
    [
        "short1!",  # too short
        "lowercaseonlypassword!",  # no uppercase
        "UPPERCASEONLYPASSWORD!",  # no lowercase
        "NoSpecialChar123",  # no special character
    ],
)
@pytest.mark.asyncio
async def test_password_policy_rejects_invalid_passwords(admin_service, password):
    with pytest.raises(ValidationError):
        await admin_service._enforce_password_policy(password)
