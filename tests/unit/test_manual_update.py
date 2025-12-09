"""
Test for manual update functionality (PUT /api/v1/manuals/{manual_id})

RFP Reference: FR-4 (Manual update and management)
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import RecordNotFoundError, ValidationError
from app.models.manual import ManualEntry, ManualStatus
from app.schemas.manual import ManualEntryUpdate
from app.services.manual_service import ManualService


class DummyLLM:
    """더미 LLM 클라이언트"""

    model = "dummy-model"

    async def complete_json(self, *args, **kwargs):
        return {}

    async def complete(self, *args, **kwargs):
        return {"content": "summary"}


class FakeManualRepository:
    """테스트용 매뉴얼 저장소"""

    def __init__(self):
        self._store: dict[UUID, ManualEntry] = {}

    async def get_by_id(self, manual_id: UUID) -> ManualEntry | None:
        return self._store.get(manual_id)

    async def update(self, manual: ManualEntry) -> ManualEntry:
        self._store[manual.id] = manual
        return manual

    async def create(self, manual: ManualEntry) -> ManualEntry:
        self._store[manual.id] = manual
        return manual

    async def find_by_ids(self, ids: list[UUID]) -> list[ManualEntry]:
        return [m for m in self._store.values() if m.id in ids]

    async def list_entries(self, statuses=None, limit=100):
        entries = list(self._store.values())
        if statuses:
            entries = [e for e in entries if e.status in statuses]
        return entries[:limit]


class FakeVersionRepository:
    """테스트용 버전 저장소"""

    async def get_latest_version(self):
        return None

    async def list_versions(self, limit=100):
        return []


class FakeReviewRepository:
    """테스트용 리뷰 저장소"""

    pass


class FakeConsultationRepository:
    """테스트용 상담 저장소"""

    pass


@pytest.fixture
def manual_repo():
    """매뉴얼 저장소 fixture"""
    return FakeManualRepository()


@pytest.fixture
def version_repo():
    """버전 저장소 fixture"""
    return FakeVersionRepository()


@pytest.fixture
def review_repo():
    """리뷰 저장소 fixture"""
    return FakeReviewRepository()


@pytest.fixture
def consultation_repo():
    """상담 저장소 fixture"""
    return FakeConsultationRepository()


@pytest.fixture
def service(manual_repo, version_repo, review_repo, consultation_repo):
    """ManualService fixture"""
    return ManualService(
        session=None,  # 테스트에서는 사용 안 함
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        version_repo=version_repo,
        review_repo=review_repo,
        consultation_repo=consultation_repo,
    )


@pytest.fixture
def draft_manual():
    """DRAFT 상태 매뉴얼 fixture"""
    return ManualEntry(
        id=uuid4(),
        keywords=["계정", "잠금"],
        topic="계정 잠금 해제 방법",
        background="고객이 계정이 잠겨있어서 로그인할 수 없는 상황",
        guideline="계정 상태 확인\n고객의 아이디를 확인하여 계정 잠김 여부를 확인합니다.",
        business_type="인터넷뱅킹",
        error_code="ACC_LOCKED",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def approved_manual():
    """APPROVED 상태 매뉴얼 fixture"""
    return ManualEntry(
        id=uuid4(),
        keywords=["대출", "신청"],
        topic="대출 신청 절차",
        background="고객이 대출을 신청하고 싶어하는 상황",
        guideline="고객 정보 확인\n신용도 검사\n대출 승인",
        business_type="대출",
        error_code="LOAN_APPLY",
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_update_manual_draft_success(service, manual_repo, draft_manual):
    """DRAFT 상태 메뉴얼 업데이트 성공 케이스"""
    # 준비
    await manual_repo.create(draft_manual)

    # 요청 데이터
    payload = ManualEntryUpdate(
        topic="계정 잠금 해제",
        keywords=["계정", "해제"],
    )

    # 실행
    result = await service.update_manual(draft_manual.id, payload)

    # 검증
    assert result.id == draft_manual.id
    assert result.topic == "계정 잠금 해제"
    assert result.keywords == ["계정", "해제"]
    # 기존 값은 유지되어야 함
    assert result.background == draft_manual.background
    assert result.guideline == draft_manual.guideline


@pytest.mark.asyncio
async def test_update_manual_partial_fields(service, manual_repo, draft_manual):
    """DRAFT 메뉴얼 부분 필드 업데이트"""
    # 준비
    await manual_repo.create(draft_manual)
    original_keywords = draft_manual.keywords
    original_background = draft_manual.background

    # 요청 데이터 (topic만 업데이트)
    payload = ManualEntryUpdate(topic="새로운 주제")

    # 실행
    result = await service.update_manual(draft_manual.id, payload)

    # 검증
    assert result.topic == "새로운 주제"
    assert result.keywords == original_keywords
    assert result.background == original_background
    assert result.guideline == draft_manual.guideline


@pytest.mark.asyncio
async def test_update_manual_all_fields(service, manual_repo, draft_manual):
    """DRAFT 메뉴얼 모든 필드 업데이트"""
    # 준비
    await manual_repo.create(draft_manual)

    # 요청 데이터
    payload = ManualEntryUpdate(
        topic="완전히 새로운 주제",
        keywords=["새", "키", "워드"],
        background="완전히 새로운 배경",
        guideline="새로운 가이드라인\n단계 1\n단계 2",
    )

    # 실행
    result = await service.update_manual(draft_manual.id, payload)

    # 검증
    assert result.topic == "완전히 새로운 주제"
    assert result.keywords == ["새", "키", "워드"]
    assert result.background == "완전히 새로운 배경"
    assert result.guideline == "새로운 가이드라인\n단계 1\n단계 2"
    assert result.status == ManualStatus.DRAFT


@pytest.mark.asyncio
async def test_update_manual_not_found(service):
    """존재하지 않는 메뉴얼 업데이트 시도"""
    # 준비
    non_existent_id = uuid4()

    # 요청 데이터
    payload = ManualEntryUpdate(topic="새 주제")

    # 실행 및 검증
    with pytest.raises(RecordNotFoundError):
        await service.update_manual(non_existent_id, payload)


@pytest.mark.asyncio
async def test_update_manual_approved_status_fails(service, manual_repo, draft_manual):
    """DRAFT가 아닌 상태 메뉴얼 업데이트 시도 실패"""
    # 준비
    draft_manual.status = ManualStatus.APPROVED
    await manual_repo.create(draft_manual)

    # 요청 데이터
    payload = ManualEntryUpdate(topic="새 주제")

    # 실행 및 검증
    with pytest.raises(ValidationError) as exc_info:
        await service.update_manual(draft_manual.id, payload)

    assert "DRAFT 상태인 메뉴얼만 수정 가능합니다" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_manual_cannot_change_to_approved(service, manual_repo, draft_manual):
    """APPROVED 상태로 변경하려고 할 때 실패 (별도 approve 엔드포인트 사용 필수)"""
    # 준비
    await manual_repo.create(draft_manual)

    # 요청 데이터 (status를 APPROVED로 변경 시도)
    payload = ManualEntryUpdate(status=ManualStatus.APPROVED)

    # 실행 및 검증
    with pytest.raises(ValidationError) as exc_info:
        await service.update_manual(draft_manual.id, payload)

    assert "APPROVED 상태로 변경하려면 /approve 엔드포인트를 사용하세요" in str(exc_info.value)


@pytest.mark.asyncio
async def test_update_manual_status_to_deprecated(service, manual_repo, draft_manual):
    """DRAFT에서 DEPRECATED 상태로 변경"""
    # 준비
    await manual_repo.create(draft_manual)

    # 요청 데이터
    payload = ManualEntryUpdate(status=ManualStatus.DEPRECATED)

    # 실행
    result = await service.update_manual(draft_manual.id, payload)

    # 검증
    assert result.status == ManualStatus.DEPRECATED


@pytest.mark.asyncio
async def test_update_manual_empty_payload(service, manual_repo, draft_manual):
    """빈 업데이트 요청 (아무 필드도 제공하지 않음)"""
    # 준비
    await manual_repo.create(draft_manual)

    # 요청 데이터 (아무 필드도 없음)
    payload = ManualEntryUpdate()

    # 실행
    result = await service.update_manual(draft_manual.id, payload)

    # 검증 (변경이 없어야 함)
    assert result.topic == draft_manual.topic
    assert result.keywords == draft_manual.keywords
    assert result.background == draft_manual.background
    assert result.guideline == draft_manual.guideline
    assert result.status == draft_manual.status


@pytest.mark.asyncio
async def test_update_manual_deprecated_status_fails(service, manual_repo, draft_manual):
    """DEPRECATED 상태 메뉴얼은 수정 불가"""
    # 준비
    draft_manual.status = ManualStatus.DEPRECATED
    await manual_repo.create(draft_manual)

    # 요청 데이터
    payload = ManualEntryUpdate(topic="새 주제")

    # 실행 및 검증
    with pytest.raises(ValidationError) as exc_info:
        await service.update_manual(draft_manual.id, payload)

    assert "DRAFT 상태인 메뉴얼만 수정 가능합니다" in str(exc_info.value)
