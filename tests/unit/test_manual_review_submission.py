"""
Manual Review Task Submission Tests (FR-6)

검토 태스크 시작 기능 테스트:
- TODO 상태 → IN_PROGRESS 상태 전환
- 상태 변경 이력 기록
- 태스크 조회
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import ManualReviewTask, TaskStatus
from app.models.manual import ManualEntry
from app.repositories.manual_rdb import (
    ManualEntryRDBRepository,
    ManualReviewTaskRepository,
)
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.services.task_service import TaskService
from app.services.manual_service import ManualService
from app.core.exceptions import RecordNotFoundError


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock AsyncSession"""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_task_repo() -> AsyncMock:
    """Mock ManualReviewTaskRepository"""
    return AsyncMock(spec=ManualReviewTaskRepository)


@pytest.fixture
def mock_manual_repo() -> AsyncMock:
    """Mock ManualEntryRDBRepository"""
    return AsyncMock(spec=ManualEntryRDBRepository)


@pytest.fixture
def mock_common_code_repo() -> AsyncMock:
    """Mock CommonCodeItemRepository"""
    return AsyncMock(spec=CommonCodeItemRepository)


@pytest.fixture
def mock_manual_service() -> AsyncMock:
    """Mock ManualService"""
    return AsyncMock(spec=ManualService)


@pytest.fixture
def task_service(
    mock_session: AsyncMock,
    mock_task_repo: AsyncMock,
    mock_manual_repo: AsyncMock,
    mock_common_code_repo: AsyncMock,
    mock_manual_service: AsyncMock,
) -> TaskService:
    """TaskService 인스턴스 생성"""
    service = TaskService(
        session=mock_session,
        manual_service=mock_manual_service,
        task_repo=mock_task_repo,
        manual_repo=mock_manual_repo,
        common_code_item_repo=mock_common_code_repo,
    )
    return service


class TestStartReviewTask:
    """검토 태스크 시작 (TODO → IN_PROGRESS) 테스트"""

    @pytest.mark.asyncio
    async def test_start_task_success(
        self,
        task_service: TaskService,
        mock_task_repo: AsyncMock,
        mock_manual_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """검토 태스크 시작 - 성공"""
        # Arrange
        task_id = uuid4()

        # 신규 메뉴얼 생성
        new_manual = MagicMock(spec=ManualEntry)
        new_manual.id = uuid4()
        new_manual.topic = "인터넷뱅킹 로그인 오류"
        new_manual.background = "로그인 시도 중 오류 발생"
        new_manual.business_type = "인터넷뱅킹"
        new_manual.error_code = "ERR_LOGIN_001"
        new_manual.keywords = ["로그인", "오류", "해결"]

        # 검토 태스크 생성
        task = MagicMock(spec=ManualReviewTask)
        task.id = task_id
        task.status = TaskStatus.TODO
        task.old_entry_id = None
        task.new_entry_id = new_manual.id
        task.similarity = 0.92
        task.reviewer_id = None
        task.review_notes = None
        task.created_at = MagicMock()
        task.updated_at = MagicMock()

        # Mock 설정
        mock_task_repo.get_by_id.return_value = task
        mock_manual_repo.get_by_id.return_value = new_manual
        mock_session.flush = AsyncMock()
        mock_task_repo.update = AsyncMock()

        # Act
        result = await task_service.start_task(task_id)

        # Assert
        assert result.status == TaskStatus.IN_PROGRESS
        assert result.id == task_id
        mock_task_repo.get_by_id.assert_called_once_with(task_id)
        mock_session.flush.assert_called()
        mock_task_repo.update.assert_called_once()

        # 상태 변경 확인
        assert task.status == TaskStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_start_task_not_found(
        self,
        task_service: TaskService,
        mock_task_repo: AsyncMock,
    ) -> None:
        """검토 태스크 시작 - 태스크 없음"""
        # Arrange
        task_id = uuid4()
        mock_task_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(RecordNotFoundError):
            await task_service.start_task(task_id)

    @pytest.mark.asyncio
    async def test_start_task_records_history(
        self,
        task_service: TaskService,
        mock_task_repo: AsyncMock,
        mock_manual_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """검토 태스크 시작 - 히스토리 기록 확인"""
        # Arrange
        task_id = uuid4()

        new_manual = MagicMock(spec=ManualEntry)
        new_manual.id = uuid4()
        new_manual.topic = "테스트"
        new_manual.background = "테스트 배경"
        new_manual.business_type = "인터넷뱅킹"
        new_manual.error_code = "ERR_001"
        new_manual.keywords = ["테스트"]

        task = MagicMock(spec=ManualReviewTask)
        task.id = task_id
        task.status = TaskStatus.TODO
        task.old_entry_id = None
        task.new_entry_id = new_manual.id
        task.similarity = 0.85
        task.reviewer_id = None
        task.review_notes = None
        task.created_at = MagicMock()
        task.updated_at = MagicMock()

        mock_task_repo.get_by_id.return_value = task
        mock_manual_repo.get_by_id.return_value = new_manual
        mock_session.flush = AsyncMock()
        mock_task_repo.update = AsyncMock()

        # Act
        await task_service.start_task(task_id)

        # Assert
        # session.add()가 호출되어 히스토리가 추가되어야 함
        assert mock_session.add.called
        # 추가된 항목이 TaskHistory 타입인지는 테스트하기 어렵지만,
        # session.add()가 호출되었는지 확인함

    @pytest.mark.asyncio
    async def test_start_task_changes_status(
        self,
        task_service: TaskService,
        mock_task_repo: AsyncMock,
        mock_manual_repo: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """검토 태스크 시작 - 상태 변경 확인"""
        # Arrange
        task_id = uuid4()

        new_manual = MagicMock(spec=ManualEntry)
        new_manual.id = uuid4()
        new_manual.topic = "테스트"
        new_manual.background = "테스트 배경"
        new_manual.business_type = "인터넷뱅킹"
        new_manual.error_code = "ERR_001"
        new_manual.keywords = ["테스트"]

        initial_status = TaskStatus.TODO
        task = MagicMock(spec=ManualReviewTask)
        task.id = task_id
        task.status = initial_status
        task.old_entry_id = None
        task.new_entry_id = new_manual.id
        task.similarity = 0.85
        task.reviewer_id = None
        task.review_notes = None
        task.created_at = MagicMock()
        task.updated_at = MagicMock()

        mock_task_repo.get_by_id.return_value = task
        mock_manual_repo.get_by_id.return_value = new_manual
        mock_session.flush = AsyncMock()
        mock_task_repo.update = AsyncMock()

        # Act
        await task_service.start_task(task_id)

        # Assert
        # 태스크의 상태가 변경되어야 함
        assert task.status == TaskStatus.IN_PROGRESS
        # update()가 호출되어야 함
        mock_task_repo.update.assert_called_once_with(task)
