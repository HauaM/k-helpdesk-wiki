"""
Unit tests for DepartmentService
"""

import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.services.department_service import DepartmentService
from app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
)
from app.core.exceptions import RecordNotFoundError, DuplicateRecordError


# Database setup for tests
@pytest.fixture
async def async_db_session():
    """
    Create in-memory SQLite database for testing
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_local = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    async with async_session_local() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def department_service(async_db_session):
    return DepartmentService(session=async_db_session)


@pytest.mark.asyncio
async def test_update_department(department_service):
    """
    Test updating a department
    """
    # Create department
    create_payload = DepartmentCreate(
        department_code="DEPT01",
        department_name="인사팀",
        is_active=True,
    )
    created = await department_service.create_department(create_payload)

    # Update department
    update_payload = DepartmentUpdate(
        department_code="DEPT01_UPDATED",
        department_name="인사총무팀",
        is_active=False,
    )
    updated = await department_service.update_department(created.id, update_payload)

    assert updated.id == created.id
    assert updated.department_code == "DEPT01_UPDATED"
    assert updated.department_name == "인사총무팀"
    assert updated.is_active is False

    # Verify generic list fetch reflects update
    fetched = await department_service.list_departments(department_code="DEPT01_UPDATED")
    assert len(fetched) == 1
    assert fetched[0].department_name == "인사총무팀"


@pytest.mark.asyncio
async def test_update_department_duplicate_code(department_service):
    """
    Test updating a department with a duplicate code
    """
    # Create two departments
    await department_service.create_department(
        DepartmentCreate(department_code="DEPT01", department_name="Team 1")
    )
    dept2 = await department_service.create_department(
        DepartmentCreate(department_code="DEPT02", department_name="Team 2")
    )

    # Try to update dept2 to use DEPT01's code
    with pytest.raises(DuplicateRecordError):
        await department_service.update_department(
            dept2.id,
            DepartmentUpdate(department_code="DEPT01", department_name="Team 2 Updated"),
        )


@pytest.mark.asyncio
async def test_update_department_not_found(department_service):
    """
    Test updating a non-existent department
    """
    with pytest.raises(RecordNotFoundError):
        await department_service.update_department(
            uuid4(),
            DepartmentUpdate(department_code="NEW", department_name="New"),
        )
