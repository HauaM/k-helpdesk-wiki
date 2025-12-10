"""
Tests for menu version group management (Phase 3).

RFP Reference:
- FR-5: Manual version management
- FR-14: Manual diff + version listing
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import sqltypes
from sqlalchemy.types import TypeDecorator

from app.models import Base, Consultation, ManualEntry, ManualStatus, ManualVersion
from app.repositories.manual_rdb import ManualVersionRepository
from app.schemas.manual import ManualApproveRequest
from app.services.manual_service import ManualService


class MockLLMClient:
    """Minimal LLM client stub for tests."""

    model = "mock"

    async def complete_json(self, *args, **kwargs):
        return {}

    async def complete(self, *args, **kwargs):
        return {"content": "mocked"}


class MockVectorStore:
    """No-op vector store."""

    async def index_document(self, *args, **kwargs):
        return None


@pytest.fixture
async def async_engine():
    """Create in-memory SQLite engine and initialize schema.

    Note: SQLite doesn't support PostgreSQL-specific types (JSONB, ARRAY, UUID).
    We convert these to SQLite-compatible types before table creation.
    """

    # Convert PostgreSQL types to SQLite-compatible types
    @event.listens_for(Base.metadata, "before_create")
    def receive_before_create(metadata, connection, **kw):
        """Convert PostgreSQL-specific types to SQLite-compatible types."""
        # Don't use sorted_tables (has circular dependency issues)
        # Instead, iterate through all tables directly
        for table in metadata.tables.values():
            for column in table.columns:
                # Convert JSONB -> JSON
                if isinstance(column.type, JSONB):
                    column.type = sqltypes.JSON()
                # Convert ARRAY -> JSON (SQLite doesn't have native array type)
                elif isinstance(column.type, ARRAY):
                    column.type = sqltypes.JSON()
                # Convert UUID -> String (CHAR(32))
                elif isinstance(column.type, UUID):
                    column.type = String(32)

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
def async_session_factory(async_engine):
    """Async session factory for tests."""
    return sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


@pytest.fixture
async def async_db_session(async_session_factory):
    """Yield a database session."""
    async with async_session_factory() as session:
        yield session


@pytest.fixture
async def manual_service(async_db_session):
    """ManualService instance backed by the test session."""
    return ManualService(
        session=async_db_session,
        llm_client=MockLLMClient(),
        vectorstore=MockVectorStore(),
    )


async def create_consultation(session: AsyncSession, business_type: str, error_code: str):
    """Helper to create a consultation used as ManualEntry source."""
    consultation = Consultation(
        summary="모의 상담",
        inquiry_text="문의 내용",
        action_taken="처리 내용",
        branch_code="BR001",
        employee_id="emp1",
        business_type=business_type,
        error_code=error_code,
    )
    session.add(consultation)
    await session.flush()
    return consultation


async def create_manual_entry(
    session: AsyncSession,
    *,
    business_type: str,
    error_code: str,
    topic: str = "테스트 메뉴얼",
) -> ManualEntry:
    """Create a draft manual entry tied to a consultation."""
    consultation = await create_consultation(session, business_type, error_code)
    manual = ManualEntry(
        topic=topic,
        keywords=["키워드"],
        background="배경 설명",
        guideline="절차1\n설명1",
        business_type=business_type,
        error_code=error_code,
        source_consultation_id=consultation.id,
        status=ManualStatus.DRAFT,
    )
    session.add(manual)
    await session.flush()
    return manual


@pytest.mark.asyncio
async def test_repo_manual_version_unique_constraint_per_group(async_db_session: AsyncSession):
    """T1: 동일 버전 번호가 그룹별로 독립적으로 존재할 수 있어야 함."""
    repo = ManualVersionRepository(async_db_session)

    version_a = ManualVersion(
        version="1",
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    version_b = ManualVersion(
        version="1",
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )
    async_db_session.add_all([version_a, version_b])
    await async_db_session.flush()

    assert version_a.version == version_b.version == "1"
    assert version_a.id != version_b.id


@pytest.mark.asyncio
async def test_repo_get_latest_version_with_group_filter(async_db_session: AsyncSession):
    """T2: 그룹 필터링을 적용해 최신 버전이 선택되는지 확인."""
    repo = ManualVersionRepository(async_db_session)
    now = datetime.now(timezone.utc)

    versions = [
        ManualVersion(
            version="1",
            business_type="인터넷뱅킹",
            error_code="ERR_LOGIN_001",
            created_at=now,
            updated_at=now,
        ),
        ManualVersion(
            version="2",
            business_type="인터넷뱅킹",
            error_code="ERR_LOGIN_001",
            created_at=now + timedelta(days=1),
            updated_at=now + timedelta(days=1),
        ),
        ManualVersion(
            version="1",
            business_type="모바일뱅킹",
            error_code="ERR_OTP_002",
            created_at=now + timedelta(days=2),
            updated_at=now + timedelta(days=2),
        ),
    ]
    async_db_session.add_all(versions)
    await async_db_session.flush()

    latest_a = await repo.get_latest_version(
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
    )
    latest_b = await repo.get_latest_version(
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
    )

    assert latest_a.version == "2"
    assert latest_b.version == "1"


@pytest.mark.asyncio
async def test_service_approve_manual_assigns_group_version(
    async_db_session: AsyncSession, manual_service: ManualService
):
    """T3: 각 그룹은 독립적인 버전 시퀀스를 유지해야 함."""
    manual_a = await create_manual_entry(
        async_db_session,
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        topic="로그인 오류",
    )
    result_a = await manual_service.approve_manual(
        manual_a.id, ManualApproveRequest(approver_id="reviewer1")
    )
    assert result_a.version == "1"

    manual_b = await create_manual_entry(
        async_db_session,
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        topic="OTP 오류",
    )
    result_b = await manual_service.approve_manual(
        manual_b.id, ManualApproveRequest(approver_id="reviewer1")
    )
    assert result_b.version == "1"


@pytest.mark.asyncio
async def test_service_concurrent_approval_multiple_groups(
    async_db_session: AsyncSession, manual_service: ManualService
):
    """T4: 다른 그룹의 메뉴얼이 승인될 때 버전 충돌이 없어야 함.

    Note: SQLite doesn't support true concurrent transactions,
    so we test sequential approval with small delays instead.
    Both groups should get version="1" independently.
    """
    manual_a = await create_manual_entry(
        async_db_session,
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        topic="동시 로그인 오류",
    )
    manual_b = await create_manual_entry(
        async_db_session,
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        topic="동시 OTP 오류",
    )

    # Approve sequentially with small delay (SQLite limitation)
    result_a = await manual_service.approve_manual(
        manual_a.id, ManualApproveRequest(approver_id="reviewer1")
    )
    await asyncio.sleep(1.0)  # 1 second for SQLite second precision
    result_b = await manual_service.approve_manual(
        manual_b.id, ManualApproveRequest(approver_id="reviewer1")
    )

    assert result_a.version == "1"
    assert result_b.version == "1"


@pytest.mark.asyncio
async def test_service_list_versions_returns_group_versions_only(
    async_db_session: AsyncSession, manual_service: ManualService
):
    """T5: list_versions()는 동일 그룹 버전만 반환해야 함."""
    manual_a = await create_manual_entry(
        async_db_session,
        business_type="인터넷뱅킹",
        error_code="ERR_LOGIN_001",
        topic="버전 목록 A",
    )
    for _ in range(3):
        await manual_service.approve_manual(
            manual_a.id, ManualApproveRequest(approver_id="reviewer1")
        )
        manual_a.status = ManualStatus.DRAFT
        manual_a.version_id = None
        await async_db_session.flush()
        await asyncio.sleep(1.0)  # Ensure different timestamps (1 second for SQLite second precision)

    manual_b = await create_manual_entry(
        async_db_session,
        business_type="모바일뱅킹",
        error_code="ERR_OTP_002",
        topic="버전 목록 B",
    )
    for _ in range(2):
        await manual_service.approve_manual(
            manual_b.id, ManualApproveRequest(approver_id="reviewer1")
        )
        manual_b.status = ManualStatus.DRAFT
        manual_b.version_id = None
        await async_db_session.flush()
        await asyncio.sleep(1.0)  # Ensure different timestamps (1 second for SQLite second precision)

    versions_a = await manual_service.list_versions(manual_a.id)
    versions_b = await manual_service.list_versions(manual_b.id)

    assert [v.value for v in versions_a] == ["3", "2", "1"]
    assert [v.value for v in versions_b] == ["2", "1"]
