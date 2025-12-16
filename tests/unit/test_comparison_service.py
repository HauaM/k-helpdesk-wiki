"""
Unit tests for ComparisonService (FR-11 v2.1)

Tests cover:
- SIMILAR comparison path (similarity >= 0.95)
- SUPPLEMENT comparison path (0.7 <= similarity < 0.95)
- NEW comparison path (similarity < 0.7)
- Auto-latest manual selection
- User-selected manual selection
- VectorStore error handling (graceful fallback)
- Metadata filtering for cross-group contamination prevention
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ComparisonType
from app.services.comparison_service import (
    ComparisonService,
    ComparisonResult,
    COMPARISON_VERSION,
)
from app.repositories.manual_rdb import ManualEntryRDBRepository
from app.vectorstore.protocol import VectorSearchResult
from app.core.exceptions import RecordNotFoundError, VectorSearchError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_manual_repo():
    """Mock ManualEntryRDBRepository"""
    return AsyncMock(spec=ManualEntryRDBRepository)


@pytest.fixture
def mock_vectorstore():
    """Mock VectorStore"""
    vec = AsyncMock()
    vec.similarity.return_value = 0.5
    return vec


@pytest.fixture
def mock_session():
    """Mock AsyncSession"""
    return AsyncMock()


@pytest.fixture
def comparison_service(mock_session, mock_manual_repo, mock_vectorstore):
    """ComparisonService instance with mocked dependencies"""
    service = ComparisonService(
        session=mock_session,
        manual_repo=mock_manual_repo,
        vectorstore=mock_vectorstore,
    )
    return service


@pytest.fixture
def sample_draft_manual():
    """Sample draft manual entry"""
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
    )


@pytest.fixture
def sample_approved_manual():
    """Sample approved manual entry"""
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
    )


@pytest.fixture(autouse=True)
def default_candidates(mock_manual_repo, sample_approved_manual):
    mock_manual_repo.find_all_approved_by_group.return_value = [sample_approved_manual]


@pytest.fixture
def sample_deprecated_manual():
    """Sample deprecated manual entry"""
    return ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="구 로그인 실패 처리",
        keywords=["로그인"],
        background="예전 버전",
        guideline="구 버전 가이드",
        status=ManualStatus.DEPRECATED,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


# ============================================================================
# Test: SIMILAR Comparison (similarity >= 0.95)
# ============================================================================


@pytest.mark.asyncio
async def test_compare_similar_auto_latest(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Auto-select latest approved manual when similarity >= 0.95

    Path: SIMILAR
    - Similarity score is high (0.97)
    - Result should be ComparisonType.SIMILAR
    - Should return existing_manual
    """
    # Setup
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.97

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,  # Auto-select
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )

    # Assert
    assert isinstance(result, ComparisonResult)
    assert result.comparison_type == ComparisonType.SIMILAR
    assert result.existing_manual is not None
    assert result.existing_manual.id == sample_approved_manual.id
    assert result.similarity_score == 0.97

    # Verify VectorStore.similarity was called
    mock_vectorstore.similarity.assert_called_once()


@pytest.mark.asyncio
async def test_compare_similar_user_selected(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Use user-selected manual when compare_with_manual_id provided

    Path: SIMILAR
    - User explicitly selected a manual
    - Should compare with that specific manual
    - Result: SIMILAR if similarity >= 0.95
    """
    # Setup
    mock_manual_repo.get_by_id.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.96

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=str(sample_approved_manual.id),
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )

    # Assert
    assert result.comparison_type == ComparisonType.SIMILAR
    assert result.existing_manual.id == sample_approved_manual.id


# ============================================================================
# Test: SUPPLEMENT Comparison (0.7 <= similarity < 0.95)
# ============================================================================


@pytest.mark.asyncio
async def test_compare_supplement(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Supplement path when 0.7 <= similarity < 0.95

    Path: SUPPLEMENT
    - Similarity is medium (0.82)
    - Result should be ComparisonType.SUPPLEMENT
    - Should create review task for approval
    """
    # Setup
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.82

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )

    # Assert
    assert result.comparison_type == ComparisonType.SUPPLEMENT
    assert result.existing_manual is not None
    assert result.existing_manual.id == sample_approved_manual.id
    assert result.similarity_score == 0.82


# ============================================================================
# Test: NEW Comparison (similarity < 0.7)
# ============================================================================


@pytest.mark.asyncio
async def test_compare_new_no_similar_found(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual
):
    """
    Test: NEW path when no existing manual found

    Path: NEW
    - No existing approved manual in same group
    - Result should be ComparisonType.NEW
    - Should return None for existing_manual
    """
    # Setup
    mock_manual_repo.find_latest_by_group.return_value = None

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )

    # Assert
    assert result.comparison_type == ComparisonType.NEW


@pytest.mark.asyncio
async def test_compare_assigns_compare_version(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual
):
    """
    ComparisonResult.compare_version should be populated with the runtime key.
    """
    mock_vectorstore.similarity.return_value = 0.75

    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    assert result.compare_version == COMPARISON_VERSION


@pytest.mark.asyncio
async def test_find_best_match_candidate_prefers_high_score(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual
):
    """
    find_best_match_candidate should return the instance with highest similarity.
    """
    manual_low = ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="low score",
        keywords=["low"],
        background="low",
        guideline="low",
        status=ManualStatus.APPROVED,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    manual_high = ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="high score",
        keywords=["high"],
        background="high",
        guideline="high",
        status=ManualStatus.APPROVED,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    mock_manual_repo.find_all_approved_by_group.return_value = [manual_low, manual_high]

    mock_vectorstore.similarity.side_effect = [0.4, 0.85]

    best_match = await comparison_service.find_best_match_candidate(sample_draft_manual)

    assert best_match is not None
    assert best_match.id == manual_high.id


@pytest.mark.asyncio
async def test_compare_new_low_similarity(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: NEW path when similarity < 0.7

    Path: NEW
    - Similarity score is low (0.65)
    - Result should be ComparisonType.NEW
    - Should ignore the low-similarity match
    """
    # Setup
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.65

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )

    # Assert
    assert result.comparison_type == ComparisonType.NEW
    assert result.existing_manual is None


# ============================================================================
# Test: Cross-Group Contamination Prevention
# ============================================================================


@pytest.mark.asyncio
async def test_metadata_filter_prevents_cross_group_comparison(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual
):
    """
    Test: Only compares within same business_type/error_code group

    Security: find_latest_by_group should be called with correct group keys
    - Draft: business_type="인터넷뱅킹", error_code="E001"
    - Ensure no cross-group comparison occurs
    """
    # Setup: No manual found in group
    mock_manual_repo.find_latest_by_group.return_value = None

    # Execute
    await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    # Assert: find_latest_by_group was called with correct parameters
    mock_manual_repo.find_latest_by_group.assert_called_once()
    call_kwargs = mock_manual_repo.find_latest_by_group.call_args.kwargs
    assert call_kwargs["business_type"] == "인터넷뱅킹"
    assert call_kwargs["error_code"] == "E001"


# ============================================================================
# Test: VectorStore Error Handling
# ============================================================================


@pytest.mark.asyncio
async def test_vectorstore_error_graceful_fallback(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Graceful fallback to NEW when VectorStore fails

    Resilience: If VectorStore throws error, should not crash
    - Exception: VectorSearchError
    - Result: ComparisonType.NEW (safe default)
    """
    # Setup: Manual found, but VectorStore throws error during similarity
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.side_effect = VectorSearchError("Connection timeout")

    # Execute: Should not raise, should fallback gracefully
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    # Assert: Fallback to NEW
    assert result.comparison_type == ComparisonType.NEW
    assert result.existing_manual is None
    assert result.similarity_score is None


@pytest.mark.asyncio
async def test_vectorstore_unavailable_fallback(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual
):
    """
    Test: Handle VectorStore unavailable gracefully

    Resilience: If VectorStore is None, should fallback
    """
    # Setup: VectorStore is None
    comparison_service.vectorstore = None

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    # Assert: Fallback to NEW
    assert result.comparison_type == ComparisonType.NEW
    assert result.existing_manual is None


# ============================================================================
# Test: User-Selected Manual Lookup
# ============================================================================


@pytest.mark.asyncio
async def test_user_selected_manual_not_found(
    comparison_service, mock_manual_repo,
    sample_draft_manual
):
    """
    Test: Handle case when user-selected manual doesn't exist

    Error handling: Should fallback to NEW
    """
    # Setup: Manual doesn't exist
    selected_manual_id = uuid4()
    mock_manual_repo.get_by_id.return_value = None

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=selected_manual_id,
    )

    # Assert: Should fallback to NEW
    assert result.comparison_type == ComparisonType.NEW
    assert result.existing_manual is None


# ============================================================================
# Test: Manual Exclusion in Auto-Latest Selection
# ============================================================================


@pytest.mark.asyncio
async def test_exclude_draft_itself_from_results(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Auto-latest selects approved manual, not the draft itself

    Logic: find_latest_by_group has exclude_id parameter to avoid drafts
    """
    # Setup: find_latest_by_group returns approved manual (not the draft)
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.97

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    # Assert: Should pick approved, not draft
    assert result.comparison_type in [ComparisonType.SIMILAR, ComparisonType.SUPPLEMENT]
    assert result.existing_manual is not None
    assert result.existing_manual.id == sample_approved_manual.id
    assert result.existing_manual.id != sample_draft_manual.id


# ============================================================================
# Test: Result Data Structure
# ============================================================================


@pytest.mark.asyncio
async def test_comparison_result_structure(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: ComparisonResult structure is correct

    Verify: All required fields are populated correctly
    """
    # Setup
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.95

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
    )

    # Assert: All fields present and correct type
    assert isinstance(result, ComparisonResult)
    assert hasattr(result, "comparison_type")
    assert hasattr(result, "existing_manual")
    assert hasattr(result, "similarity_score")
    assert result.comparison_type in [
        ComparisonType.SIMILAR,
        ComparisonType.SUPPLEMENT,
        ComparisonType.NEW,
    ]
    if result.similarity_score is not None:
        assert isinstance(result.similarity_score, float)
        assert 0.0 <= result.similarity_score <= 1.0


# ============================================================================
# Test: Custom Threshold Parameters
# ============================================================================


@pytest.mark.asyncio
async def test_custom_thresholds(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Custom similarity thresholds are respected

    Config: similarity_threshold_similar and similarity_threshold_supplement
    """
    # Setup: Similarity of 0.80 with custom thresholds
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.80

    # Test 1: With default thresholds (0.95, 0.7)
    # 0.80 should be SUPPLEMENT (0.7 <= 0.80 < 0.95)
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.95,
        similarity_threshold_supplement=0.7,
    )
    assert result.comparison_type == ComparisonType.SUPPLEMENT

    # Test 2: With custom thresholds (0.85, 0.75)
    # 0.80 should still be SUPPLEMENT (0.75 <= 0.80 < 0.85)
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.85,
        similarity_threshold_supplement=0.75,
    )
    assert result.comparison_type == ComparisonType.SUPPLEMENT


# ============================================================================
# Test: Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_similarity_boundary_similar(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Boundary case at similarity_threshold_similar (>= 0.95)

    Boundary: 0.95 should be SIMILAR, not SUPPLEMENT
    """
    # Setup: Exactly at threshold
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.95

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_similar=0.95,
    )

    # Assert: Should be SIMILAR (not SUPPLEMENT)
    assert result.comparison_type == ComparisonType.SIMILAR


@pytest.mark.asyncio
async def test_similarity_boundary_supplement(
    comparison_service, mock_manual_repo, mock_vectorstore,
    sample_draft_manual, sample_approved_manual
):
    """
    Test: Boundary case at similarity_threshold_supplement (>= 0.7)

    Boundary: 0.7 should be SUPPLEMENT, not NEW
    """
    # Setup: Exactly at threshold
    mock_manual_repo.find_latest_by_group.return_value = sample_approved_manual
    mock_vectorstore.similarity.return_value = 0.7

    # Execute
    result = await comparison_service.compare(
        new_draft=sample_draft_manual,
        compare_with_manual_id=None,
        similarity_threshold_supplement=0.7,
    )

    # Assert: Should be SUPPLEMENT (not NEW)
    assert result.comparison_type == ComparisonType.SUPPLEMENT


@pytest.mark.asyncio
async def test_empty_draft_manual(
    comparison_service, mock_manual_repo, mock_vectorstore
):
    """
    Test: Handle empty/incomplete draft manual gracefully

    Edge case: Minimal draft with no keywords/background
    """
    # Setup: Minimal draft
    minimal_draft = ManualEntry(
        id=uuid4(),
        business_type="인터넷뱅킹",
        error_code="E001",
        topic="",  # Empty
        keywords=[],  # Empty
        background="",  # Empty
        guideline="",  # Empty
        status=ManualStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    mock_manual_repo.find_latest_by_group.return_value = None

    # Execute: Should not crash
    result = await comparison_service.compare(
        new_draft=minimal_draft,
        compare_with_manual_id=None,
    )

    # Assert: Fallback to NEW
    assert result.comparison_type == ComparisonType.NEW
