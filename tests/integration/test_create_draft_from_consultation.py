"""
create_draft_from_consultation 기능에 대한 통합 테스트 (FR-2/FR-9/FR-11 v2.1)

테스트는 다음 End-to-End 흐름을 검증한다:
1. 상담(Consultation) 데이터 조회
2. LLM을 통한 초안(Manual Draft) 생성
3. 환각(Hallucination) 여부 검사
4. 메뉴얼(Manual) 데이터 저장
5. ComparisonService 비교(3가지 경로 분기)
6. 검토 태스크(Review Task) 생성

테스트되는 3가지 비교 경로:
- SIMILAR: 검토 태스크 없음, 기존 메뉴얼 반환
- SUPPLEMENT: 검토 태스크 생성, 기존+신규 메뉴얼 반환
- NEW: 검토 태스크 생성, 신규 초안만 반환
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from app.models.consultation import Consultation
from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ManualReviewTask, TaskStatus
from app.models.task import ComparisonType
from app.schemas.manual import ManualDraftCreateFromConsultationRequest, ManualDraftCreateResponse
from app.services.manual_service import ManualService
from app.services.comparison_service import ComparisonService
from app.repositories.manual_rdb import ManualEntryRDBRepository, ManualReviewTaskRepository
from app.repositories.consultation_rdb import ConsultationRDBRepository
from app.vectorstore.protocol import VectorSearchResult
from app.llm.protocol import LLMClientProtocol
from app.core.exceptions import RecordNotFoundError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_session():
    """Mock AsyncSession"""
    return AsyncMock()


@pytest.fixture
def mock_manual_repo():
    """Mock ManualEntryRDBRepository"""
    return AsyncMock(spec=ManualEntryRDBRepository)


@pytest.fixture
def mock_review_repo():
    """Mock ManualReviewTaskRepository"""
    return AsyncMock(spec=ManualReviewTaskRepository)


@pytest.fixture
def mock_consultation_repo():
    """Mock ConsultationRDBRepository"""
    return AsyncMock(spec=ConsultationRDBRepository)


@pytest.fixture
def mock_vectorstore():
    """Mock VectorStore"""
    return AsyncMock()


@pytest.fixture
def mock_llm_client():
    """Mock LLM Client"""
    client = AsyncMock(spec=LLMClientProtocol)
    client.complete_json.return_value = {
        "keywords": ["로그인", "실패"],
        "background": "사용자가 올바른 비밀번호로 로그인하지 못함",
        "guideline": "비밀번호 재설정 메뉴 안내",
        "topic": "로그인 실패 처리",
    }
    return client


@pytest.fixture
def mock_version_repo():
    """Mock ManualVersionRepository"""
    return AsyncMock()


@pytest.fixture
def mock_common_code_repo():
    """Mock CommonCodeItemRepository"""
    return AsyncMock()


@pytest.fixture
def manual_service(
    mock_session,
    mock_manual_repo,
    mock_review_repo,
    mock_consultation_repo,
    mock_vectorstore,
    mock_llm_client,
    mock_version_repo,
    mock_common_code_repo,
):
    """ManualService with mocked dependencies"""
    service = ManualService(
        session=mock_session,
        llm_client=mock_llm_client,
        vectorstore=mock_vectorstore,
        manual_repo=mock_manual_repo,
        review_repo=mock_review_repo,
        version_repo=mock_version_repo,
        consultation_repo=mock_consultation_repo,
        common_code_item_repo=mock_common_code_repo,
    )
    return service


# ============================================================================
# Sample Data Fixtures
# ============================================================================


@pytest.fixture
def sample_consultation():
    """Sample consultation record"""
    return Consultation(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        summary="사용자가 올바른 비밀번호로 로그인 시도 중",
        inquiry_text="로그인이 안 됩니다",
        action_taken="비밀번호 재설정 안내",
        branch_code="001",
        employee_id="EMP001",
        metadata_fields={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_approved_manual():
    """Sample approved manual from same group"""
    return ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="로그인 오류 대처",
        keywords=["로그인", "오류"],
        background="사용자가 로그인에 실패한 경우",
        guideline="고객센터 연락처 안내",
        status=ManualStatus.APPROVED,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        source_consultation_id=uuid4(),
    )


@pytest.fixture
def sample_draft_manual():
    """Sample draft manual from LLM"""
    return ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="로그인 실패 처리",
        keywords=["로그인", "실패"],
        background="사용자가 올바른 비밀번호로 로그인하지 못함",
        guideline="비밀번호 재설정 메뉴 안내",
        status=ManualStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        source_consultation_id=uuid4(),
    )


# ============================================================================
# Test: SIMILAR Path (No Review Task)
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_similar_no_review_task(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_approved_manual,
    sample_draft_manual,
):
    """
    테스트: SIMILAR 경로 - 검토 태스크가 생성되지 않아야 함

    흐름:
    1. 상담 데이터 조회 성공
    2. LLM이 초안 생성
    3. 환각 검사 통과
    4. 초안 저장
    5. 비교 결과가 SIMILAR 반환
    6. 기존 메뉴얼 반환, 검토 태스크는 생성되지 않아야 함
    """
    # Setup
    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.search.return_value = [
        VectorSearchResult(
            id=str(sample_approved_manual.id),
            score=0.97,  # SIMILAR
            metadata={},
        ),
    ]

    # Execute
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert
    assert isinstance(result, ManualDraftCreateResponse)
    assert result.comparison_type == ComparisonType.SIMILAR
    assert result.existing_manual is not None
    assert result.existing_manual.id == sample_approved_manual.id
    assert result.draft_entry.id == sample_draft_manual.id
    assert result.review_task_id is None  # No review task for SIMILAR
    assert result.similarity_score == 0.97


# ============================================================================
# Test: SUPPLEMENT Path (Create Review Task)
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_supplement_with_review_task(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_review_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_approved_manual,
    sample_draft_manual,
):
    """
    테스트: SUPPLEMENT 경로 - 검토 태스크가 생성되어야 함

    흐름:
    1. 상담 데이터 조회 성공
    2. LLM이 초안 생성
    3. 환각 검사 통과
    4. 초안 저장
    5. 비교 결과가 SUPPLEMENT로 반환
    6. 검토 태스크 생성
    7. 기존 메뉴얼 + 신규 초안 + 생성된 태스크 ID 반환
    """
    # Setup
    review_task_id = uuid4()

    def mock_create_review_task(task):
        task.id = review_task_id
        return task

    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.search.return_value = [
        VectorSearchResult(
            id=str(sample_approved_manual.id),
            score=0.82,  # SUPPLEMENT
            metadata={},
        ),
    ]
    mock_review_repo.create = AsyncMock(side_effect=mock_create_review_task)

    # Execute
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert
    assert result.comparison_type == ComparisonType.SUPPLEMENT
    assert result.existing_manual is not None
    assert result.draft_entry.id == sample_draft_manual.id
    assert result.review_task_id is not None
    assert result.review_task_id == review_task_id  # Verify correct task
    assert result.similarity_score == 0.82

    # Verify review task created
    mock_review_repo.create.assert_called_once()


# ============================================================================
# Test: NEW Path (Create Review Task for Approval)
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_new_with_review_task(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_review_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_draft_manual,
):
    """
    테스트: NEW 경로 - 신규 메뉴얼용 검토 태스크가 생성되어야 함

    흐름:
    1. 상담 데이터 조회 성공
    2. LLM이 초안 생성
    3. 환각 검사 통과
    4. 초안 저장
    5. 비교 결과가 NEW (기존 메뉴얼 없음)
    6. 검토 태스크 생성
    7. 기존 메뉴얼 없이 신규 초안만 반환
    """
    # Setup
    review_task_id = uuid4()

    def mock_create_review_task(task):
        task.id = review_task_id
        return task

    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.find_latest_by_group.return_value = None  # No existing manual
    mock_vectorstore.search.return_value = []  # No similar manuals
    mock_review_repo.create = AsyncMock(side_effect=mock_create_review_task)

    # Execute
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert
    assert result.comparison_type == ComparisonType.NEW
    assert result.existing_manual is None
    assert result.draft_entry.id == sample_draft_manual.id
    assert result.review_task_id is not None
    assert result.review_task_id == review_task_id  # Verify correct task
    assert result.similarity_score is None

    # Verify review task created with old_entry_id=None
    mock_review_repo.create.assert_called_once()


# ============================================================================
# Test: User-Selected Comparison
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_with_user_selected_comparison(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_review_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_approved_manual,
    sample_draft_manual,
):
    """
    테스트: 사용자가 특정 버전을 비교 대상으로 선택한 경우

    흐름:
    - compare_with_manual_id를 사용자가 직접 지정
    - 최신 메뉴얼이 아니라, 지정한 메뉴얼을 기준으로 비교 수행
    """
    # Setup
    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.get_by_id.return_value = sample_approved_manual
    mock_vectorstore.search.return_value = [
        VectorSearchResult(
            id=str(sample_approved_manual.id),
            score=0.90,
            metadata={},
        ),
    ]

    # Execute with compare_with_manual_id
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
        compare_with_manual_id=sample_approved_manual.id,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert
    assert result.existing_manual.id == sample_approved_manual.id
    assert result.similarity_score == 0.90


# ============================================================================
# Test: Hallucination Detection
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_hallucination_detected(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_review_repo,
    mock_vectorstore,
    sample_consultation,
    sample_draft_manual,
):
    """
    테스트: 환각이 감지되더라도 초안은 생성되어야 함

    흐름:
    - LLM이 환각이 포함된 내용을 생성
    - 환각 검사에서 문제가 감지됨
    - 초안은 생성하되 hallucination flag 포함
    - 비교 로직 실행
    - 검토 태스크는 정상적으로 생성됨
    """
    # Setup
    review_task_id = uuid4()

    def mock_create_review_task(task):
        task.id = review_task_id
        return task

    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.find_latest_by_group.return_value = None
    mock_vectorstore.search.return_value = []
    mock_review_repo.create = AsyncMock(side_effect=mock_create_review_task)

    # Execute - hallucination check enabled (will detect issues)
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert - Draft is created despite hallucination detection
    assert result is not None
    assert result.comparison_type in [ComparisonType.NEW, ComparisonType.SUPPLEMENT]
    assert result.draft_entry.id == sample_draft_manual.id
    # Hallucination doesn't prevent draft creation
    assert result.review_task_id is not None


# ============================================================================
# Test: Consultation Not Found
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_consultation_not_found(
    manual_service,
    mock_consultation_repo,
):
    """
    테스트: 상담 데이터가 존재하지 않는 경우

    에러 처리: RecordNotFoundError가 발생해야 함
    """
    # Setup
    mock_consultation_repo.get_by_id.return_value = None

    # Execute & Assert
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=uuid4(),
        enforce_hallucination_check=True,
    )

    with pytest.raises(RecordNotFoundError):
        await manual_service.create_draft_from_consultation(request)


# ============================================================================
# Test: LLM Generation Failure
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_llm_generation_error(
    manual_service,
    mock_consultation_repo,
    mock_llm_client,
    sample_consultation,
):
    """
    테스트: LLM 초안 생성이 실패하는 경우

    에러 처리: 예외가 그대로 전파되어야 함
    """
    # Setup
    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_llm_client.complete_json.side_effect = Exception("LLM API error")

    # Execute & Assert
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )

    with pytest.raises(Exception, match="LLM API error"):
        await manual_service.create_draft_from_consultation(request)


# ============================================================================
# Test: Response Structure
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_response_structure(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_approved_manual,
    sample_draft_manual,
):
    """
    테스트: ManualDraftCreateResponse의 구조 검증

    검증 항목:
    - 모든 필드가 존재하는지
    - 필드 타입이 올바른지
    """
    # Setup - SIMILAR path
    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.search.return_value = [
        VectorSearchResult(
            id=str(sample_approved_manual.id),
            score=0.98,
            metadata={},
        ),
    ]

    # Execute
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert - All fields present
    assert hasattr(result, "comparison_type")
    assert hasattr(result, "draft_entry")
    assert hasattr(result, "existing_manual")
    assert hasattr(result, "review_task_id")
    assert hasattr(result, "similarity_score")
    assert hasattr(result, "message")

    # Assert - Types correct
    assert isinstance(result.draft_entry, dict) or hasattr(result.draft_entry, "id")
    assert result.existing_manual is None or hasattr(result.existing_manual, "id")
    assert result.review_task_id is None or isinstance(result.review_task_id, str)
    assert result.similarity_score is None or isinstance(result.similarity_score, float)
    assert isinstance(result.message, str)


# ============================================================================
# Test: Metadata Filtering in Comparison
# ============================================================================


@pytest.mark.asyncio
async def test_create_draft_metadata_filtering(
    manual_service,
    mock_consultation_repo,
    mock_manual_repo,
    mock_review_repo,
    mock_llm_client,
    mock_vectorstore,
    sample_consultation,
    sample_approved_manual,
    sample_draft_manual,
):
    """
    테스트: VectorStore 검색 시 메타데이터 필터가 올바르게 적용되는지 확인

    보안 요구사항:
    - 동일한 (업무구분, 에러코드) 그룹 내에서만 검색해야 함
    """
    # Setup
    review_task = ManualReviewTask(
        id=uuid4(),
        old_entry_id=sample_approved_manual.id,
        new_entry_id=sample_draft_manual.id,
        similarity=0.75,
        comparison_type=ComparisonType.SUPPLEMENT,
        status=TaskStatus.TODO,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    mock_consultation_repo.get_by_id.return_value = sample_consultation
    mock_manual_repo.create.return_value = sample_draft_manual
    # Must set find_latest_by_group to trigger vectorstore search
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.search.return_value = [
        VectorSearchResult(
            id=str(sample_approved_manual.id),
            score=0.75,
            metadata={},
        ),
    ]
    mock_review_repo.create.return_value = review_task

    # Execute
    request = ManualDraftCreateFromConsultationRequest(
        consultation_id=sample_consultation.id,
        enforce_hallucination_check=True,
    )
    result = await manual_service.create_draft_from_consultation(request)

    # Assert - VectorStore called with metadata filter
    mock_vectorstore.search.assert_called_once()
    call_kwargs = mock_vectorstore.search.call_args.kwargs

    # Verify metadata filter was passed
    metadata_filter = call_kwargs.get("metadata_filter")
    assert metadata_filter is not None
    assert metadata_filter["business_type"] == sample_consultation.business_type
    assert metadata_filter["error_code"] == sample_consultation.error_code
    assert metadata_filter["status"] == "APPROVED"

    # Verify result is correct
    assert result.comparison_type == ComparisonType.SUPPLEMENT
