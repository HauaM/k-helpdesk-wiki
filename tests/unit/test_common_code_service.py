"""
Unit tests for CommonCodeService (FR-15)
"""

import pytest
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, CommonCodeGroup, CommonCodeItem
from app.services.common_code_service import (
    CommonCodeService,
    FORBIDDEN_KEYWORD_GROUP_CODE,
)
from app.schemas.common_code import (
    CommonCodeGroupCreate,
    CommonCodeGroupUpdate,
    CommonCodeItemCreate,
    CommonCodeItemUpdate,
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


# Service fixture
@pytest.fixture
async def common_code_service(async_db_session):
    """
    Create CommonCodeService with test database
    """
    return CommonCodeService(session=async_db_session)


# ==================== Group CRUD Tests ====================


@pytest.mark.asyncio
async def test_create_group(common_code_service):
    """
    Test creating a common code group
    """
    payload = CommonCodeGroupCreate(
        group_code="BUSINESS_TYPE",
        group_name="업무 구분",
        description="비즈니스 타입 코드",
        is_active=True,
    )

    result = await common_code_service.create_group(payload)

    assert result.group_code == "BUSINESS_TYPE"
    assert result.group_name == "업무 구분"
    assert result.description == "비즈니스 타입 코드"
    assert result.is_active is True
    assert result.id is not None


@pytest.mark.asyncio
async def test_create_group_duplicate(common_code_service):
    """
    Test that duplicate group codes are rejected
    """
    payload = CommonCodeGroupCreate(
        group_code="ERROR_CODE",
        group_name="에러 코드",
    )

    # Create first group
    await common_code_service.create_group(payload)

    # Try to create duplicate
    with pytest.raises(DuplicateRecordError):
        await common_code_service.create_group(payload)


@pytest.mark.asyncio
async def test_get_group(common_code_service):
    """
    Test retrieving a group by ID
    """
    # Create group
    payload = CommonCodeGroupCreate(
        group_code="BRANCH_CODE",
        group_name="지점 코드",
    )
    created = await common_code_service.create_group(payload)

    # Retrieve group
    result = await common_code_service.get_group(created.id)

    assert result.id == created.id
    assert result.group_code == "BRANCH_CODE"


@pytest.mark.asyncio
async def test_get_group_not_found(common_code_service):
    """
    Test retrieving non-existent group
    """
    fake_id = uuid4()

    with pytest.raises(RecordNotFoundError):
        await common_code_service.get_group(fake_id)


@pytest.mark.asyncio
async def test_get_group_by_code(common_code_service):
    """
    Test retrieving a group by code
    """
    # Create group
    payload = CommonCodeGroupCreate(
        group_code="BUSINESS_TYPE",
        group_name="업무 구분",
    )
    created = await common_code_service.create_group(payload)

    # Retrieve by code
    result = await common_code_service.get_group_by_code("BUSINESS_TYPE")

    assert result.id == created.id
    assert result.group_code == "BUSINESS_TYPE"


@pytest.mark.asyncio
async def test_list_groups(common_code_service):
    """
    Test listing groups with pagination
    """
    # Create multiple groups
    for i in range(5):
        payload = CommonCodeGroupCreate(
            group_code=f"GROUP_{i}",
            group_name=f"그룹 {i}",
        )
        await common_code_service.create_group(payload)

    # List groups
    result = await common_code_service.list_groups(page=1, page_size=3)

    assert result.total == 5
    assert len(result.items) == 3
    assert result.page == 1
    assert result.page_size == 3
    assert result.total_pages == 2


@pytest.mark.asyncio
async def test_update_group(common_code_service):
    """
    Test updating a group
    """
    # Create group
    create_payload = CommonCodeGroupCreate(
        group_code="OLD_CODE",
        group_name="이전 이름",
    )
    created = await common_code_service.create_group(create_payload)

    # Update group
    update_payload = CommonCodeGroupUpdate(
        group_name="새로운 이름",
        description="새로운 설명",
    )
    updated = await common_code_service.update_group(created.id, update_payload)

    assert updated.group_code == "OLD_CODE"  # Code unchanged
    assert updated.group_name == "새로운 이름"
    assert updated.description == "새로운 설명"


@pytest.mark.asyncio
async def test_delete_group(common_code_service):
    """
    Test deleting a group
    """
    # Create group
    payload = CommonCodeGroupCreate(
        group_code="DELETE_ME",
        group_name="삭제할 그룹",
    )
    created = await common_code_service.create_group(payload)

    # Delete group
    await common_code_service.delete_group(created.id)

    # Verify deleted
    with pytest.raises(RecordNotFoundError):
        await common_code_service.get_group(created.id)


# ==================== Item CRUD Tests ====================


@pytest.mark.asyncio
async def test_create_item(common_code_service):
    """
    Test creating a common code item
    """
    # Create group first
    group_payload = CommonCodeGroupCreate(
        group_code="BUSINESS_TYPE",
        group_name="업무 구분",
    )
    group = await common_code_service.create_group(group_payload)

    # Create item
    item_payload = CommonCodeItemCreate(
        code_key="RETAIL",
        code_value="리테일",
        sort_order=1,
        is_active=True,
    )
    result = await common_code_service.create_item(group.id, item_payload)

    assert result.code_key == "RETAIL"
    assert result.code_value == "리테일"
    assert result.sort_order == 1
    assert result.is_active is True
    assert result.group_id == group.id


@pytest.mark.asyncio
async def test_create_item_duplicate(common_code_service):
    """
    Test that duplicate code keys are rejected within a group
    """
    # Create group
    group_payload = CommonCodeGroupCreate(
        group_code="ERROR_CODE",
        group_name="에러 코드",
    )
    group = await common_code_service.create_group(group_payload)

    # Create first item
    item_payload = CommonCodeItemCreate(
        code_key="ERROR_001",
        code_value="시스템 오류",
    )
    await common_code_service.create_item(group.id, item_payload)

    # Try to create duplicate
    with pytest.raises(DuplicateRecordError):
        await common_code_service.create_item(group.id, item_payload)


@pytest.mark.asyncio
async def test_get_item(common_code_service):
    """
    Test retrieving an item by ID
    """
    # Setup: create group and item
    group_payload = CommonCodeGroupCreate(
        group_code="TEST_GROUP",
        group_name="테스트 그룹",
    )
    group = await common_code_service.create_group(group_payload)

    item_payload = CommonCodeItemCreate(
        code_key="TEST_KEY",
        code_value="테스트 값",
    )
    created = await common_code_service.create_item(group.id, item_payload)

    # Retrieve item
    result = await common_code_service.get_item(created.id)

    assert result.id == created.id
    assert result.code_key == "TEST_KEY"
    assert result.code_value == "테스트 값"


@pytest.mark.asyncio
async def test_list_items_by_group(common_code_service):
    """
    Test listing items by group with pagination
    """
    # Create group
    group_payload = CommonCodeGroupCreate(
        group_code="LOAN_TYPE",
        group_name="대출 유형",
    )
    group = await common_code_service.create_group(group_payload)

    # Create multiple items
    for i in range(5):
        item_payload = CommonCodeItemCreate(
            code_key=f"LOAN_{i}",
            code_value=f"대출 {i}",
            sort_order=i,
        )
        await common_code_service.create_item(group.id, item_payload)

    # List items
    result = await common_code_service.list_items_by_group(
        group.id, page=1, page_size=3
    )

    assert result.total == 5
    assert len(result.items) == 3
    assert result.page == 1
    assert result.total_pages == 2


@pytest.mark.asyncio
async def test_update_item(common_code_service):
    """
    Test updating an item
    """
    # Setup
    group_payload = CommonCodeGroupCreate(
        group_code="STATUS",
        group_name="상태",
    )
    group = await common_code_service.create_group(group_payload)

    item_payload = CommonCodeItemCreate(
        code_key="ACTIVE",
        code_value="활성",
    )
    created = await common_code_service.create_item(group.id, item_payload)

    # Update item
    update_payload = CommonCodeItemUpdate(
        code_value="활성화됨",
        sort_order=10,
    )
    updated = await common_code_service.update_item(created.id, update_payload)

    assert updated.code_key == "ACTIVE"  # Key unchanged
    assert updated.code_value == "활성화됨"
    assert updated.sort_order == 10


@pytest.mark.asyncio
async def test_delete_item(common_code_service):
    """
    Test deleting an item
    """
    # Setup
    group_payload = CommonCodeGroupCreate(
        group_code="DELETE_TEST",
        group_name="삭제 테스트",
    )
    group = await common_code_service.create_group(group_payload)

    item_payload = CommonCodeItemCreate(
        code_key="DELETE_ME",
        code_value="삭제할 항목",
    )
    created = await common_code_service.create_item(group.id, item_payload)

    # Delete item
    await common_code_service.delete_item(created.id)

    # Verify deleted
    with pytest.raises(RecordNotFoundError):
        await common_code_service.get_item(created.id)


# ==================== Public API Tests ====================


@pytest.mark.asyncio
async def test_get_codes_by_group_code(common_code_service):
    """
    Test getting codes by group code (frontend API)
    """
    # Setup
    group_payload = CommonCodeGroupCreate(
        group_code="BUSINESS_TYPE",
        group_name="업무 구분",
    )
    group = await common_code_service.create_group(group_payload)

    for code_key, code_value in [("RETAIL", "리테일"), ("LOAN", "대출")]:
        item_payload = CommonCodeItemCreate(
            code_key=code_key,
            code_value=code_value,
        )
        await common_code_service.create_item(group.id, item_payload)

    # Test get codes by group code
    result = await common_code_service.get_codes_by_group_code("BUSINESS_TYPE")

    assert result.group_code == "BUSINESS_TYPE"
    assert len(result.items) == 2
    assert result.items[0].code_key in ["RETAIL", "LOAN"]


@pytest.mark.asyncio
async def test_get_multiple_code_groups(common_code_service):
    """
    Test getting multiple code groups at once (bulk API)
    """
    # Setup: create multiple groups with items
    groups = [
        ("BUSINESS_TYPE", "업무 구분", [("RETAIL", "리테일"), ("LOAN", "대출")]),
        ("ERROR_CODE", "에러 코드", [("ERROR_001", "시스템 오류")]),
    ]

    for group_code, group_name, items in groups:
        group_payload = CommonCodeGroupCreate(
            group_code=group_code,
            group_name=group_name,
        )
        group = await common_code_service.create_group(group_payload)

        for code_key, code_value in items:
            item_payload = CommonCodeItemCreate(
                code_key=code_key,
                code_value=code_value,
            )
            await common_code_service.create_item(group.id, item_payload)

    # Test bulk get
    result = await common_code_service.get_multiple_code_groups(
        ["BUSINESS_TYPE", "ERROR_CODE"]
    )

    assert "BUSINESS_TYPE" in result.data
    assert "ERROR_CODE" in result.data
    assert len(result.data["BUSINESS_TYPE"].items) == 2
    assert len(result.data["ERROR_CODE"].items) == 1


# ==================== Attribute Tests ====================


@pytest.mark.asyncio
async def test_item_with_attributes(common_code_service):
    """
    Test creating item with custom attributes
    """
    # Setup
    group_payload = CommonCodeGroupCreate(
        group_code="WITH_ATTRS",
        group_name="속성 포함 그룹",
    )
    group = await common_code_service.create_group(group_payload)

    # Create item with attributes
    item_payload = CommonCodeItemCreate(
        code_key="SPECIAL",
        code_value="특수",
        attributes={"color": "red", "icon": "star"},
    )
    result = await common_code_service.create_item(group.id, item_payload)

    assert result.attributes == {"color": "red", "icon": "star"}

    # Retrieve and verify attributes
    retrieved = await common_code_service.get_item(result.id)
    assert retrieved.attributes == {"color": "red", "icon": "star"}


@pytest.mark.asyncio
async def test_get_forbidden_keywords_returns_values(common_code_service):
    """
    금칙 키워드 그룹이 있을 경우 code_value 목록을 반환해야 한다.
    """
    group_payload = CommonCodeGroupCreate(
        group_code=FORBIDDEN_KEYWORD_GROUP_CODE,
        group_name="금칙 키워드",
    )
    group = await common_code_service.create_group(group_payload)

    item_payload = CommonCodeItemCreate(
        code_key="BLOCKED",
        code_value="금칙",
        sort_order=1,
    )
    await common_code_service.create_item(group.id, item_payload)

    result = await common_code_service.get_forbidden_keywords()

    assert result == ["금칙"]


@pytest.mark.asyncio
async def test_get_forbidden_keywords_empty_without_items(common_code_service):
    """
    항목이 없으면 빈 리스트를 반환해야 한다.
    """
    group_payload = CommonCodeGroupCreate(
        group_code=FORBIDDEN_KEYWORD_GROUP_CODE,
        group_name="금칙 키워드",
    )
    await common_code_service.create_group(group_payload)

    result = await common_code_service.get_forbidden_keywords()
    assert result == []
