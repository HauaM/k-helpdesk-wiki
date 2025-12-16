"""
Test for manual version API functionality

RFP Reference: FR-14 (Manual version comparison)
- API 1: GET /api/v1/manuals/{manual_id}/versions
- API 2: GET /api/v1/manuals/{manual_id}/versions/{version}
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import RecordNotFoundError
from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.services.manual_service import parse_guideline_string, ManualService


class DummyLLM:
    """더미 LLM 클라이언트"""

    model = "dummy-model"

    async def complete_json(self, *args, **kwargs):
        return {}

    async def complete(self, *args, **kwargs):
        return {"content": "summary"}


class FakeManualRepository:
    """테스트용 메뉴얼 저장소"""

    def __init__(self):
        self._store: dict[UUID, ManualEntry] = {}

    async def get_by_id(self, manual_id: UUID) -> ManualEntry | None:
        return self._store.get(manual_id)

    async def find_by_ids(self, ids: list[UUID]) -> list[ManualEntry]:
        return [m for m in self._store.values() if m.id in ids]

    async def find_by_version(
        self, version_id: UUID, statuses=None
    ) -> list[ManualEntry]:
        entries = [e for e in self._store.values() if e.version_id == version_id]
        if statuses:
            entries = [e for e in entries if e.status in statuses]
        return entries

    async def find_by_business_and_error(
        self, business_type: str | None, error_code: str | None, statuses=None
    ) -> list[ManualEntry]:
        """같은 business_type/error_code를 가진 메뉴얼들 조회"""
        entries = [
            e
            for e in self._store.values()
            if e.business_type == business_type and e.error_code == error_code
        ]
        if statuses:
            entries = [e for e in entries if e.status in statuses]
        return entries

    async def create(self, manual: ManualEntry) -> ManualEntry:
        self._store[manual.id] = manual
        return manual

    async def update(self, manual: ManualEntry) -> ManualEntry:
        self._store[manual.id] = manual
        return manual


class FakeVersionRepository:
    """테스트용 버전 저장소"""

    def __init__(self):
        self._store: dict[UUID, ManualVersion] = {}
        self._version_map: dict[str, UUID] = {}

    async def get_latest_version(self) -> ManualVersion | None:
        if not self._store:
            return None
        # 가장 최근에 생성된 버전 반환
        return max(self._store.values(), key=lambda v: v.created_at)

    async def get_by_version(self, version: str) -> ManualVersion | None:
        version_id = self._version_map.get(version)
        if version_id:
            return self._store.get(version_id)
        return None

    async def list_versions(
        self,
        business_type: str | None = None,
        error_code: str | None = None,
        limit: int = 100,
    ) -> list[ManualVersion]:
        """Mock list_versions matching real repository signature"""
        versions = list(self._store.values())
        
        # Filter by business_type and error_code if provided
        if business_type is not None:
            versions = [v for v in versions if v.business_type == business_type]
        if error_code is not None:
            versions = [v for v in versions if v.error_code == error_code]
        
        # Sort by creation time (most recent first)
        versions.sort(key=lambda v: v.created_at, reverse=True)
        
        # Apply limit
        return versions[:limit]

    async def create(self, version: ManualVersion) -> ManualVersion:
        self._store[version.id] = version
        self._version_map[version.version] = version.id
        return version


class FakeReviewRepository:
    """테스트용 리뷰 저장소"""

    pass


class FakeConsultationRepository:
    """테스트용 상담 저장소"""

    pass


@pytest.fixture
def manual_repo():
    """메뉴얼 저장소 fixture"""
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
        session=None,
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        version_repo=version_repo,
        review_repo=review_repo,
        consultation_repo=consultation_repo,
    )


@pytest.fixture
def version_v2_1():
    """v2.1 버전 fixture (최신 버전)"""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    return ManualVersion(
        id=uuid4(),
        version="v2.1",
        description="Latest version",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def version_v2_0():
    """v2.0 버전 fixture (이전 버전)"""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    # v2.0은 v2.1보다 1일 이전에 생성
    past = now - timedelta(days=1)
    return ManualVersion(
        id=uuid4(),
        version="v2.0",
        description="Previous version",
        created_at=past,
        updated_at=past,
    )


@pytest.fixture
def approved_manual_v2_1(version_v2_1):
    """v2.1에 속하는 APPROVED 메뉴얼 fixture"""
    now = datetime.now(timezone.utc)
    return ManualEntry(
        id=uuid4(),
        keywords=["인터넷뱅킹", "로그인오류", "E001"],
        topic="인터넷뱅킹 로그인 오류 처리 가이드",
        background="고객이 인터넷뱅킹 로그인 시 오류가 발생하는 경우는 다양한 원인이 있을 수 있습니다.",
        guideline="계정 상태 확인\n고객의 아이디를 확인하여 계정 잠김 여부를 확인합니다.\n브라우저 및 보안프로그램 점검\n고객이 사용 중인 브라우저 버전을 확인합니다.",
        business_type="인터넷뱅킹",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
        version_id=version_v2_1.id,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def approved_manual_v2_0(version_v2_0):
    """v2.0에 속하는 APPROVED 메뉴얼 fixture"""
    now = datetime.now(timezone.utc)
    return ManualEntry(
        id=uuid4(),
        keywords=["인터넷뱅킹", "로그인오류"],
        topic="인터넷뱅킹 로그인 오류 가이드",
        background="고객이 인터넷뱅킹 로그인 시 오류가 발생합니다.",
        guideline="계정 상태 확인\n고객의 계정을 확인합니다.",
        business_type="인터넷뱅킹",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
        version_id=version_v2_0.id,
        created_at=now,
        updated_at=now,
    )


# ============================================================================
# Test: parse_guideline_string (Helper function)
# ============================================================================


def test_parse_guideline_string_with_pairs():
    """제목과 설명의 쌍으로 구성된 guideline 파싱"""
    guideline = "제목1\n설명1\n제목2\n설명2"
    result = parse_guideline_string(guideline)

    assert len(result) == 2
    assert result[0]["title"] == "제목1"
    assert result[0]["description"] == "설명1"
    assert result[1]["title"] == "제목2"
    assert result[1]["description"] == "설명2"


def test_parse_guideline_string_empty():
    """빈 guideline 파싱"""
    result = parse_guideline_string("")
    assert result == []


def test_parse_guideline_string_with_extra_whitespace():
    """여백이 포함된 guideline 파싱"""
    guideline = "  제목1  \n  설명1  \n  제목2  \n  설명2  "
    result = parse_guideline_string(guideline)

    assert len(result) == 2
    assert result[0]["title"] == "제목1"
    assert result[0]["description"] == "설명1"


# ============================================================================
# Test: API 1 - GET /manuals/{manual_group_id}/versions (list_versions)
# ============================================================================


@pytest.mark.asyncio
async def test_list_versions_success(
    service, manual_repo, version_repo, version_v2_1, version_v2_0, approved_manual_v2_1, approved_manual_v2_0
):
    """버전 목록 조회 성공"""
    # 준비
    await version_repo.create(version_v2_1)
    await version_repo.create(version_v2_0)
    await manual_repo.create(approved_manual_v2_1)
    await manual_repo.create(approved_manual_v2_0)

    # 실행
    result = await service.list_versions(approved_manual_v2_1.id)

    # 검증
    assert len(result) == 2
    # 최신 버전이 먼저 나와야 함
    assert result[0].value == "v2.1"
    assert result[0].label == "v2.1 (현재 버전)"
    assert result[0].date == version_v2_1.created_at.strftime("%Y-%m-%d")

    # 이전 버전
    assert result[1].value == "v2.0"
    assert result[1].label == "v2.0"
    assert result[1].date == version_v2_0.created_at.strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_list_versions_empty(service, manual_repo):
    """빈 버전 목록 조회 (메뉴얼이 없을 때)"""
    # 실행 및 검증: 존재하지 않는 메뉴얼 ID로 호출하면 RecordNotFoundError
    with pytest.raises(RecordNotFoundError):
        await service.list_versions(uuid4())


@pytest.mark.asyncio
async def test_list_versions_single_version(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """단일 버전만 있을 때 조회"""
    # 준비
    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)

    # 실행
    result = await service.list_versions(approved_manual_v2_1.id)

    # 검증
    assert len(result) == 1
    assert result[0].label == "v2.1 (현재 버전)"


@pytest.mark.asyncio
async def test_list_versions_date_format(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """버전 날짜 형식 검증 (YYYY-MM-DD)"""
    # 준비
    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)

    # 실행
    result = await service.list_versions(approved_manual_v2_1.id)

    # 검증
    date = result[0].date
    # YYYY-MM-DD 형식인지 확인
    parts = date.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # YYYY
    assert len(parts[1]) == 2  # MM
    assert len(parts[2]) == 2  # DD


# ============================================================================
# Test: API 2 - GET /manuals/{manual_id}/versions/{version} (get_manual_by_version)
# ============================================================================


@pytest.mark.asyncio
async def test_get_manual_by_version_success(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """특정 버전의 메뉴얼 조회 성공"""
    # 준비
    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)

    # 실행
    result = await service.get_manual_by_version(approved_manual_v2_1.id, "v2.1")

    # 검증
    assert result.manual_id == approved_manual_v2_1.id
    assert result.version == "v2.1"
    assert result.topic == approved_manual_v2_1.topic
    assert result.keywords == approved_manual_v2_1.keywords
    assert result.background == approved_manual_v2_1.background
    assert result.status == ManualStatus.APPROVED


@pytest.mark.asyncio
async def test_get_manual_by_version_guideline_parsing(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """메뉴얼 조회 시 guideline 배열 변환 검증"""
    # 준비
    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)

    # 실행
    result = await service.get_manual_by_version(approved_manual_v2_1.id, "v2.1")

    # 검증: guidelines는 배열이어야 함
    assert isinstance(result.guidelines, list)
    assert len(result.guidelines) == 2

    # 첫 번째 항목
    assert result.guidelines[0].title == "계정 상태 확인"
    assert result.guidelines[0].description == "고객의 아이디를 확인하여 계정 잠김 여부를 확인합니다."

    # 두 번째 항목
    assert result.guidelines[1].title == "브라우저 및 보안프로그램 점검"
    assert (
        result.guidelines[1].description
        == "고객이 사용 중인 브라우저 버전을 확인합니다."
    )


@pytest.mark.asyncio
async def test_get_manual_by_version_version_not_found(service, approved_manual_v2_1):
    """존재하지 않는 버전으로 조회"""
    # 버전을 생성하지 않은 상태에서 조회 시도
    with pytest.raises(RecordNotFoundError) as exc_info:
        await service.get_manual_by_version(approved_manual_v2_1.id, "v99.9")

    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_manual_by_version_no_approved_entries(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """버전에 APPROVED 상태의 메뉴얼이 없는 경우"""
    # 준비
    await version_repo.create(version_v2_1)
    # DRAFT 상태의 메뉴얼만 생성
    draft_manual = approved_manual_v2_1
    draft_manual.status = ManualStatus.DRAFT
    await manual_repo.create(draft_manual)

    # 실행 및 검증
    with pytest.raises(RecordNotFoundError) as exc_info:
        await service.get_manual_by_version(draft_manual.id, "v2.1")

    assert "No approved manual entries found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_manual_by_version_response_format(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """API 응답 형식 검증"""
    # 준비
    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)

    # 실행
    result = await service.get_manual_by_version(approved_manual_v2_1.id, "v2.1")

    # 검증: 필수 필드 존재
    assert hasattr(result, "manual_id")
    assert hasattr(result, "version")
    assert hasattr(result, "topic")
    assert hasattr(result, "keywords")
    assert hasattr(result, "background")
    assert hasattr(result, "guidelines")
    assert hasattr(result, "status")
    assert hasattr(result, "updated_at")

    # 타입 검증
    assert isinstance(result.keywords, list)
    assert isinstance(result.guidelines, list)
    assert isinstance(result.status, ManualStatus)


@pytest.mark.asyncio
async def test_list_versions_excludes_draft_entries(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """DRAFT 상태 메뉴얼은 버전 목록에 포함되지 않음"""
    # 준비: version_id가 NULL인 DRAFT 메뉴얼 생성
    draft_manual = ManualEntry(
        id=uuid4(),
        keywords=["인터넷뱅킹", "로그인오류"],
        topic="DRAFT 메뉴얼",
        background="아직 승인되지 않은 초안입니다.",
        guideline="절차1\n설명1",
        business_type="인터넷뱅킹",
        error_code="E001",
        source_consultation_id=uuid4(),
        status=ManualStatus.DRAFT,
        version_id=None,  # DRAFT는 version_id가 NULL
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await version_repo.create(version_v2_1)
    await manual_repo.create(approved_manual_v2_1)
    await manual_repo.create(draft_manual)  # DRAFT 메뉴얼 추가

    # 실행: DRAFT 메뉴얼과 같은 그룹(business_type/error_code)의 버전 조회
    result = await service.list_versions(draft_manual.id)

    # 검증: DRAFT 메뉴얼은 version_id가 NULL이므로 버전 목록에 포함되지 않음
    # 대신 같은 그룹의 APPROVED 메뉴얼(approved_manual_v2_1)의 버전만 반환
    assert len(result) == 1
    assert result[0].value == "v2.1"


@pytest.mark.asyncio
async def test_list_versions_multiple_groups_isolated(
    service, manual_repo, version_repo, version_v2_1, approved_manual_v2_1
):
    """서로 다른 그룹의 메뉴얼은 버전이 격리됨"""
    # 준비: 다른 그룹(business_type/error_code)의 메뉴얼과 버전 생성
    version_v1_0 = ManualVersion(
        id=uuid4(),
        version="v1.0",
        description="Different group version",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    different_group_manual = ManualEntry(
        id=uuid4(),
        keywords=["모바일뱅킹"],
        topic="다른 그룹 메뉴얼",
        background="서로 다른 업무구분",
        guideline="절차\n설명",
        business_type="모바일뱅킹",  # 다른 business_type
        error_code="E002",  # 다른 error_code
        source_consultation_id=uuid4(),
        status=ManualStatus.APPROVED,
        version_id=None,  # 나중에 설정
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await version_repo.create(version_v2_1)
    await version_repo.create(version_v1_0)
    await manual_repo.create(approved_manual_v2_1)

    # 다른 그룹 메뉴얼의 version_id 설정
    different_group_manual.version_id = version_v1_0.id
    await manual_repo.create(different_group_manual)

    # 실행: 첫 번째 그룹의 버전 조회
    result = await service.list_versions(approved_manual_v2_1.id)

    # 검증: 같은 그룹의 버전만 반환 (v2.1만)
    assert len(result) == 1
    assert result[0].value == "v2.1"
