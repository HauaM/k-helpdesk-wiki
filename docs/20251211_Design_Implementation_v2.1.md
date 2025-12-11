# Design Document: Manual Version Management Implementation v2.1
**작성일:** 2025-12-11
**버전:** Implementation Bridge (v2.1 Spec → Code)
**목적:** v2.1 스펙 문서와 실제 구현 코드 간의 3가지 핵심 갭(gap)을 해결하기 위한 상세 설계 가이드

---

## Executive Summary

**현재 상황:**
- v2.1 스펙: 사용자 선택 가능한 버전 비교, ComparisonService 기반 comparison_type 분류 설계
- 실제 코드: 간단한 draft 생성, 충돌 검사를 분리된 endpoint로 처리

**3가지 핵심 갭:**

| 갭 | 현재 상태 | 요구 상태 | 영향 |
|-----|---------|---------|------|
| **Gap 1** | `create_draft_from_consultation()`: 단순 draft 생성 + hallucination 체크만 | 비교 로직 통합, 3-path 응답 (SIMILAR/SUPPLEMENT/NEW), 버전 선택 기능 | 스펙 미달성: 고급 비교 기능 없음 |
| **Gap 2** | `GET /{manual_id}/versions`: manual_id 사전 필요 | `GET /versions?business_type=&error_code=`: 검색 기반 발견 | UI가 버전 목록을 사전에 발견 불가 |
| **Gap 3** | `ManualReviewTask.comparison_type` 필드 부재 | 필드 추가 (similar/supplement/new) + Alembic 마이그레이션 | 비교 타입 추적 불가 |
| **Gap 4** | `vectorstore.search()`: 메타데이터 필터링 없음 | business_type + error_code 필터링 추가 | 다른 그룹 메뉴얼과 교차 비교 위험 |

---

## Part 1: Gap 1 - create_draft_from_consultation 통합 설계

### 1.1 현재 코드 상태

**파일:** `app/services/manual_service.py` (lines 125-179)

```python
async def create_draft_from_consultation(
    self, request: ManualDraftCreateFromConsultationRequest
) -> ManualDraftResponse:
    """FR-2: 상담 기반 메뉴얼 초안 생성 + FR-9 환각 방지 검증."""

    consultation = await self.consultation_repo.get_by_id(request.consultation_id)
    if consultation is None:
        raise RecordNotFoundError(...)

    source_text = f"{consultation.inquiry_text}\n{consultation.action_taken}"

    llm_payload = await self._call_llm_for_draft(...)

    has_hallucination = False
    fail_reasons: list[str] = []
    if request.enforce_hallucination_check:
        # Hallucination validation...
        has_hallucination = bool(fail_reasons)

    manual_entry = await self._persist_manual_entry(...)

    if has_hallucination:
        await self._create_review_task(
            new_entry=manual_entry,
            reason=";".join(fail_reasons) or "validation_failed",
        )

    return ManualDraftResponse.model_validate(manual_entry)  # ← 단순 응답
```

**문제점:**
- VectorStore 비교 로직 없음
- response에 comparison_type, existing_manual, task_id 미포함
- 버전 선택 기능 없음 (compare_with_manual_id param)
- 3-path 분기 (SIMILAR/SUPPLEMENT/NEW) 미구현

### 1.2 개선된 플로우 설계

#### 1.2.1 새로운 요청/응답 스키마

**파일:** `app/schemas/manual.py` - 추가할 스키마들

```python
class ManualDraftCreateFromConsultationRequest(BaseSchema):
    """개선된 draft 생성 요청 스키마"""

    consultation_id: UUID
    enforce_hallucination_check: bool = True

    # NEW: 버전 선택 기능
    # 사용자가 특정 버전과 비교하고 싶으면 해당 manual_id 지정
    # None이면 최신 APPROVED 버전과 비교
    compare_with_manual_id: UUID | None = None


class ComparisonType(str, Enum):
    """비교 결과 타입 분류 (v2.1 스펙)"""
    SIMILAR = "similar"         # ≥0.95 similarity
    SUPPLEMENT = "supplement"   # 0.7-0.95 similarity
    NEW = "new"                 # <0.7 similarity


class ManualDraftCreateResponse(BaseResponseSchema):
    """개선된 draft 생성 응답 (v2.1)

    3가지 경로:
    1. SIMILAR: 기존 메뉴얼 반환, draft 미생성
    2. SUPPLEMENT: 초안 생성 + 자동 병합 + 리뷰 태스크 생성
    3. NEW: 초안 생성 + 리뷰 태스크 생성
    """

    # 필수 필드
    comparison_type: ComparisonType
    draft_entry: ManualEntryResponse  # 항상 존재 (SIMILAR 제외)

    # 선택적 필드 - 경로별 차이
    existing_manual: ManualEntryResponse | None = None  # SIMILAR에서만
    review_task_id: UUID | None = None                  # SUPPLEMENT/NEW에서

    # 메타데이터
    similarity_score: float | None = None
    message: str  # 사용자 친화적 메시지

    # 예시:
    # SIMILAR 경로:
    # {
    #   "comparison_type": "similar",
    #   "draft_entry": {...},
    #   "existing_manual": {...},
    #   "similarity_score": 0.97,
    #   "message": "기존 메뉴얼(v1.5)과 매우 유사합니다. 기존 메뉴얼을 참고하세요."
    # }
    #
    # SUPPLEMENT 경로:
    # {
    #   "comparison_type": "supplement",
    #   "draft_entry": {...},
    #   "existing_manual": {...},
    #   "review_task_id": "uuid-xxx",
    #   "similarity_score": 0.82,
    #   "message": "기존 메뉴얼의 내용을 보충했습니다. 검토자가 확인 후 승인합니다."
    # }
    #
    # NEW 경로:
    # {
    #   "comparison_type": "new",
    #   "draft_entry": {...},
    #   "existing_manual": null,
    #   "review_task_id": "uuid-yyy",
    #   "similarity_score": null,
    #   "message": "신규 메뉴얼 초안으로 생성되었습니다."
    # }
```

#### 1.2.2 ComparisonService 설계 (신규 파일)

**파일:** `app/services/comparison_service.py` (신규 생성)

```python
"""
비교 서비스 (v2.1 구현)

VectorStore를 사용하여 신규 draft와 기존 메뉴얼을 비교하고,
유사도 점수에 따라 comparison_type을 판정한다.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.manual import ManualEntry, ManualStatus
from app.repositories.manual_rdb import ManualEntryRDBRepository
from app.vectorstore.protocol import VectorStoreProtocol

logger = get_logger(__name__)


class ComparisonType(str, Enum):
    """비교 결과 타입"""
    SIMILAR = "similar"         # ≥0.95
    SUPPLEMENT = "supplement"   # 0.7-0.95
    NEW = "new"                 # <0.7


@dataclass
class ComparisonResult:
    """비교 결과 데이터 클래스"""
    comparison_type: ComparisonType
    existing_manual: Optional[ManualEntry] = None
    similarity_score: Optional[float] = None
    reason: str = ""


class ComparisonService:
    """신규 draft와 기존 메뉴얼 비교 서비스"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        vectorstore: VectorStoreProtocol | None = None,
        manual_repo: ManualEntryRDBRepository | None = None,
    ) -> None:
        self.session = session
        self.vectorstore = vectorstore
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)

    async def compare(
        self,
        new_draft: ManualEntry,
        compare_with_manual_id: UUID | None = None,
        *,
        similarity_threshold_similar: float = 0.95,
        similarity_threshold_supplement: float = 0.7,
    ) -> ComparisonResult:
        """
        신규 draft를 기존 메뉴얼과 비교하여 comparison_type을 판정한다.

        **플로우:**
        1. compare_with_manual_id가 지정된 경우: 해당 메뉴얼과 비교
        2. 미지정: 같은 (business_type, error_code)의 최신 APPROVED 메뉴얼 찾기
        3. VectorStore에서 유사도 계산
        4. 유사도 구간에 따라 comparison_type 판정

        **Args:**
            new_draft: 신규 메뉴얼 초안
            compare_with_manual_id: 비교 대상 메뉴얼 ID (지정 시 해당 메뉴얼과 비교)
            similarity_threshold_similar: SIMILAR 판정 기준 (default: 0.95)
            similarity_threshold_supplement: SUPPLEMENT 판정 기준 (default: 0.7)

        **Returns:**
            ComparisonResult:
            - comparison_type: SIMILAR/SUPPLEMENT/NEW
            - existing_manual: 기존 메뉴얼 (NEW일 경우 None)
            - similarity_score: 유사도 점수 (NEW일 경우 None)

        **예외 처리:**
        - VectorStore 미구성: COMPARE_FAILED → NEW로 defaulting (안전 우선)
        - 비교 대상 메뉴얼 없음: NEW
        """

        # Step 1: 비교 대상 메뉴얼 결정
        target_manual = await self._get_target_manual(new_draft, compare_with_manual_id)

        if target_manual is None:
            logger.info(
                "comparison_no_target_manual",
                new_draft_id=str(new_draft.id),
                business_type=new_draft.business_type,
                error_code=new_draft.error_code,
            )
            return ComparisonResult(
                comparison_type=ComparisonType.NEW,
                reason="no_existing_manual_found",
            )

        # Step 2: VectorStore가 미구성인 경우
        if self.vectorstore is None:
            logger.warning(
                "comparison_vectorstore_unavailable",
                new_draft_id=str(new_draft.id),
                target_manual_id=str(target_manual.id),
            )
            return ComparisonResult(
                comparison_type=ComparisonType.NEW,
                reason="vectorstore_unavailable",
            )

        # Step 3: VectorStore에서 유사도 계산
        try:
            new_draft_text = self._build_manual_text(new_draft)

            # IMPORTANT: 메타데이터 필터링으로 같은 그룹만 비교
            vector_results = await self.vectorstore.search(
                query=new_draft_text,
                top_k=1,
                metadata_filters={
                    "business_type": new_draft.business_type,
                    "error_code": new_draft.error_code,
                },
            )

            if not vector_results:
                logger.info(
                    "comparison_no_vector_results",
                    new_draft_id=str(new_draft.id),
                )
                return ComparisonResult(
                    comparison_type=ComparisonType.NEW,
                    reason="no_vector_matches",
                )

            # 대상 메뉴얼이 결과에 포함되어 있는지 확인
            similarity_score = None
            for result in vector_results:
                if result.id == target_manual.id:
                    similarity_score = result.score
                    break

            if similarity_score is None:
                # 대상 메뉴얼이 검색 결과에 없음 = 유사도 낮음
                return ComparisonResult(
                    comparison_type=ComparisonType.NEW,
                    reason="target_not_in_results",
                )

            # Step 4: 유사도 구간별 판정
            if similarity_score >= similarity_threshold_similar:
                return ComparisonResult(
                    comparison_type=ComparisonType.SIMILAR,
                    existing_manual=target_manual,
                    similarity_score=similarity_score,
                    reason=f"similarity_score_{similarity_score:.2f}",
                )
            elif similarity_score >= similarity_threshold_supplement:
                return ComparisonResult(
                    comparison_type=ComparisonType.SUPPLEMENT,
                    existing_manual=target_manual,
                    similarity_score=similarity_score,
                    reason=f"similarity_score_{similarity_score:.2f}",
                )
            else:
                return ComparisonResult(
                    comparison_type=ComparisonType.NEW,
                    reason=f"similarity_below_threshold_{similarity_score:.2f}",
                )

        except Exception as e:
            logger.error(
                "comparison_error",
                error=str(e),
                new_draft_id=str(new_draft.id),
                target_manual_id=str(target_manual.id),
            )
            # VectorStore 에러 시 NEW로 안전 처리
            return ComparisonResult(
                comparison_type=ComparisonType.NEW,
                reason=f"vectorstore_error: {str(e)}",
            )

    async def _get_target_manual(
        self, new_draft: ManualEntry, compare_with_manual_id: UUID | None
    ) -> Optional[ManualEntry]:
        """
        비교 대상 메뉴얼 결정

        **로직:**
        1. compare_with_manual_id 지정 → 해당 메뉴얼 반환
        2. 미지정 → (business_type, error_code)가 같은 최신 APPROVED 메뉴얼 반환
        """

        if compare_with_manual_id is not None:
            # 사용자가 선택한 메뉴얼
            manual = await self.manual_repo.get_by_id(compare_with_manual_id)
            if manual is None:
                logger.warning(
                    "comparison_target_manual_not_found",
                    manual_id=str(compare_with_manual_id),
                )
                return None
            # 자신과 비교하는 경우 제외
            if manual.id == new_draft.id:
                return None
            return manual
        else:
            # 최신 APPROVED 메뉴얼 찾기
            latest_approved = await self.manual_repo.find_latest_by_group(
                business_type=new_draft.business_type,
                error_code=new_draft.error_code,
                status=ManualStatus.APPROVED,
                exclude_id=new_draft.id,
            )
            return latest_approved

    def _build_manual_text(self, manual: ManualEntry) -> str:
        """메뉴얼을 벡터화할 문자열로 변환"""
        # 기존 코드와 동일
        return f"{manual.topic}\n{manual.background}\n{manual.guideline}"
```

#### 1.2.3 ManualService에서 ComparisonService 통합

**파일:** `app/services/manual_service.py` - 개선된 create_draft_from_consultation

```python
class ManualService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        vectorstore: VectorStoreProtocol | None = None,
        manual_repo: ManualEntryRDBRepository | None = None,
        review_repo: ManualReviewTaskRepository | None = None,
        version_repo: ManualVersionRepository | None = None,
        consultation_repo: ConsultationRepository | None = None,
        common_code_item_repo: CommonCodeItemRepository | None = None,
        comparison_service: ComparisonService | None = None,  # NEW
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.vectorstore = vectorstore
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)
        self.review_repo = review_repo or ManualReviewTaskRepository(session)
        self.version_repo = version_repo or ManualVersionRepository(session)
        self.consultation_repo = consultation_repo or ConsultationRepository(session)
        self.common_code_item_repo = common_code_item_repo or CommonCodeItemRepository(session)
        # NEW: ComparisonService lazy 초기화
        self._comparison_service = comparison_service

    @property
    def comparison_service(self) -> ComparisonService:
        """ComparisonService lazy initialization"""
        if self._comparison_service is None:
            self._comparison_service = ComparisonService(
                session=self.session,
                vectorstore=self.vectorstore,
                manual_repo=self.manual_repo,
            )
        return self._comparison_service

    async def create_draft_from_consultation(
        self, request: ManualDraftCreateFromConsultationRequest
    ) -> ManualDraftCreateResponse:
        """FR-2/FR-9/FR-11(v2.1): 상담 기반 메뉴얼 초안 생성 + 비교 + 리뷰 태스크

        **플로우:**
        1. 상담 조회 + LLM draft 생성
        2. Hallucination 검증 (필요 시)
        3. ManualEntry 저장 (DRAFT 상태)
        4. ComparisonService로 비교
        5. comparison_type에 따라 3-path 분기:
           - SIMILAR: 기존 메뉴얼 반환, 초안 삭제 또는 아카이브
           - SUPPLEMENT: LLM으로 자동 병합, 리뷰 태스크 생성
           - NEW: 그대로 초안 유지, 리뷰 태스크 생성
        """

        # Step 1: 상담 조회
        consultation = await self.consultation_repo.get_by_id(request.consultation_id)
        if consultation is None:
            raise RecordNotFoundError(
                f"Consultation(id={request.consultation_id}) not found"
            )

        source_text = f"{consultation.inquiry_text}\n{consultation.action_taken}"

        # Step 2: LLM으로 draft 생성
        llm_payload = await self._call_llm_for_draft(
            inquiry_text=consultation.inquiry_text,
            action_taken=consultation.action_taken,
            business_type=consultation.business_type,
            error_code=consultation.error_code,
        )

        # Step 3: Hallucination 검증
        has_hallucination = False
        fail_reasons: list[str] = []
        if request.enforce_hallucination_check:
            ok_keywords, missing_kw = validate_keywords_in_source(
                llm_payload.get("keywords", []), source_text
            )
            if not ok_keywords:
                fail_reasons.append(f"missing_keywords:{','.join(missing_kw)}")

            ok_background, missing_bg = validate_sentences_subset_of_source(
                llm_payload.get("background", ""), source_text
            )
            if not ok_background:
                fail_reasons.append(f"background_missing:{len(missing_bg)}")

            ok_guideline, missing_gl = validate_sentences_subset_of_source(
                llm_payload.get("guideline", ""), source_text
            )
            if not ok_guideline:
                fail_reasons.append(f"guideline_missing:{len(missing_gl)}")

            has_hallucination = bool(fail_reasons)

        # Step 4: ManualEntry 저장 (DRAFT 상태)
        manual_entry = await self._persist_manual_entry(
            consultation_id=consultation.id,
            llm_payload=llm_payload,
            business_type=consultation.business_type,
            error_code=consultation.error_code,
            hallucination_issues=fail_reasons if has_hallucination else None,
        )

        # Step 5: ComparisonService로 비교
        comparison_result = await self.comparison_service.compare(
            new_draft=manual_entry,
            compare_with_manual_id=request.compare_with_manual_id,
        )

        # Step 6: comparison_type에 따른 분기 처리
        if comparison_result.comparison_type == ComparisonType.SIMILAR:
            # SIMILAR 경로: 기존 메뉴얼 반환, draft는 ARCHIVED로 표시
            await self.manual_repo.update(
                manual_entry.id,
                {"status": ManualStatus.ARCHIVED},
            )

            return ManualDraftCreateResponse(
                comparison_type=ComparisonType.SIMILAR,
                draft_entry=ManualEntryResponse.model_validate(manual_entry),
                existing_manual=ManualEntryResponse.model_validate(
                    comparison_result.existing_manual
                ),
                similarity_score=comparison_result.similarity_score,
                message=(
                    f"기존 메뉴얼(v{comparison_result.existing_manual.version})과 "
                    f"{comparison_result.similarity_score*100:.0f}% 유사합니다. "
                    "기존 메뉴얼을 참고하세요."
                ),
            )

        elif comparison_result.comparison_type == ComparisonType.SUPPLEMENT:
            # SUPPLEMENT 경로: 자동 병합 + 리뷰 태스크
            review_task = await self._create_review_task(
                new_entry=manual_entry,
                old_entry=comparison_result.existing_manual,
                comparison_type=ComparisonType.SUPPLEMENT,
                similarity_score=comparison_result.similarity_score,
                reason=comparison_result.reason,
                auto_merged=True,
            )

            return ManualDraftCreateResponse(
                comparison_type=ComparisonType.SUPPLEMENT,
                draft_entry=ManualEntryResponse.model_validate(manual_entry),
                existing_manual=ManualEntryResponse.model_validate(
                    comparison_result.existing_manual
                ),
                review_task_id=review_task.id,
                similarity_score=comparison_result.similarity_score,
                message=(
                    f"기존 메뉴얼(v{comparison_result.existing_manual.version})의 "
                    f"내용을 보충했습니다. 검토자가 확인 후 승인합니다."
                ),
            )

        else:  # ComparisonType.NEW
            # NEW 경로: 신규 draft, 리뷰 태스크 생성
            review_task = await self._create_review_task(
                new_entry=manual_entry,
                old_entry=None,
                comparison_type=ComparisonType.NEW,
                similarity_score=None,
                reason=comparison_result.reason,
                auto_merged=False,
            )

            return ManualDraftCreateResponse(
                comparison_type=ComparisonType.NEW,
                draft_entry=ManualEntryResponse.model_validate(manual_entry),
                existing_manual=None,
                review_task_id=review_task.id,
                similarity_score=None,
                message="신규 메뉴얼 초안으로 생성되었습니다.",
            )
```

#### 1.2.4 _create_review_task 메서드 확장

```python
async def _create_review_task(
    self,
    new_entry: ManualEntry,
    old_entry: ManualEntry | None = None,
    comparison_type: ComparisonType = ComparisonType.NEW,
    similarity_score: float | None = None,
    reason: str = "auto_detected",
    auto_merged: bool = False,
) -> ManualReviewTask:
    """
    리뷰 태스크 생성 (v2.1 확장)

    Args:
        new_entry: 신규 메뉴얼 초안
        old_entry: 기존 메뉴얼 (있으면)
        comparison_type: SIMILAR/SUPPLEMENT/NEW
        similarity_score: 유사도 점수
        reason: 태스크 생성 사유
        auto_merged: SUPPLEMENT 경로에서 자동 병합했는지 여부
    """

    task = ManualReviewTask(
        old_entry_id=old_entry.id if old_entry else None,
        new_entry_id=new_entry.id,
        similarity=similarity_score or 0.0,
        status=TaskStatus.TODO,
        decision_reason=reason,
        comparison_type=comparison_type.value,  # NEW 필드
    )

    if auto_merged and comparison_type == ComparisonType.SUPPLEMENT:
        # SUPPLEMENT 경로: LLM으로 자동 병합
        diff_json, diff_text = await self._call_llm_compare(old_entry, new_entry)
        task.review_notes = (
            f"Auto-merged via LLM. Old: {old_entry.id}, New: {new_entry.id}"
        )
        # diff_json, diff_text는 ManualReviewTaskResponse에서만 사용

    await self.review_repo.create(task)
    return task
```

### 1.3 Router 엔드포인트 업데이트

**파일:** `app/routers/manuals.py`

```python
@router.post(
    "/draft",
    response_model=ManualDraftCreateResponse,  # 변경: ManualDraftResponse → ManualDraftCreateResponse
    status_code=status.HTTP_201_CREATED,
    summary="Create manual draft from consultation (v2.1 with comparison)",
)
async def create_manual_draft(
    payload: ManualDraftCreateFromConsultationRequest,
    service: ManualService = Depends(get_manual_service),
) -> ManualDraftCreateResponse:
    """
    FR-2/FR-9/FR-11(v2.1): 상담 기반 메뉴얼 초안 생성 + 비교 + 리뷰 태스크

    **Request:**
    ```json
    {
      "consultation_id": "uuid-xxx",
      "enforce_hallucination_check": true,
      "compare_with_manual_id": "uuid-yyy"  // Optional: 특정 버전과 비교
    }
    ```

    **Response (3 가지 경로):**

    1. SIMILAR (기존 메뉴얼과 유사):
    ```json
    {
      "comparison_type": "similar",
      "draft_entry": {...},
      "existing_manual": {...},
      "similarity_score": 0.97,
      "message": "기존 메뉴얼(v1.5)과 매우 유사합니다..."
    }
    ```

    2. SUPPLEMENT (기존 메뉴얼 보충):
    ```json
    {
      "comparison_type": "supplement",
      "draft_entry": {...},
      "existing_manual": {...},
      "review_task_id": "uuid-task",
      "similarity_score": 0.82,
      "message": "기존 메뉴얼의 내용을 보충했습니다..."
    }
    ```

    3. NEW (신규 메뉴얼):
    ```json
    {
      "comparison_type": "new",
      "draft_entry": {...},
      "existing_manual": null,
      "review_task_id": "uuid-task",
      "similarity_score": null,
      "message": "신규 메뉴얼 초안으로 생성되었습니다."
    }
    ```
    """
    return await service.create_draft_from_consultation(payload)
```

---

## Part 2: Gap 2 - Version List API 설계 (검색 기반)

### 2.1 현재 코드 상태

**파일:** `app/routers/manuals.py` (lines 99-117)

```python
@router.get(
    "/{manual_id}/versions",
    response_model=list[ManualVersionResponse],
)
async def list_versions(
    manual_id: UUID,
    service: ManualService = Depends(get_manual_service),
) -> list[ManualVersionResponse]:
    """특정 메뉴얼과 같은 business_type/error_code를 가진 메뉴얼 그룹의 모든 버전"""
    return await service.list_versions(manual_id)
```

**문제점:**
- manual_id를 **사전에** 알아야 함
- UI에서 메뉴얼을 아직 생성하지 않았는데 과거 버전을 발견할 수 없음 (chicken-egg problem)

### 2.2 개선된 API 설계

#### 2.2.1 쿼리 기반 버전 조회 엔드포인트

**파일:** `app/routers/manuals.py` - 신규 엔드포인트 추가

```python
@router.get(
    "/versions",  # Note: /{manual_id}/versions보다 먼저 등록 (더 구체적)
    response_model=list[ManualVersionResponse],
    summary="Get manual versions by business type and error code",
)
async def get_versions_by_group(
    business_type: str = Query(..., description="업무 구분 (예: 인터넷뱅킹)"),
    error_code: str = Query(..., description="에러 코드 (예: E001)"),
    include_deprecated: bool = Query(
        default=False,
        description="DEPRECATED 버전 포함 여부",
    ),
    service: ManualService = Depends(get_manual_service),
) -> list[ManualVersionResponse]:
    """
    FR-11(v2.1): business_type + error_code로 메뉴얼 그룹의 버전 목록 조회

    **용도:**
    - 초안 작성 전: UI에서 과거 버전 목록 표시
    - 사용자가 특정 버전과 비교하고 싶을 때 선택

    **Query Parameters:**
    - business_type: 업무 구분 (필수)
    - error_code: 에러 코드 (필수)
    - include_deprecated: DEPRECATED 버전도 반환할지 여부 (optional)

    **Returns:**
    ```json
    [
      {
        "value": "v1.5",
        "label": "v1.5 (DEPRECATED)",
        "date": "2024-12-01",
        "status": "DEPRECATED"
      },
      {
        "value": "v1.6",
        "label": "v1.6 (현재 버전)",
        "date": "2024-12-05",
        "status": "APPROVED"
      }
    ]
    ```
    """
    try:
        return await service.get_manual_versions_by_group(
            business_type=business_type,
            error_code=error_code,
            include_deprecated=include_deprecated,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
```

#### 2.2.2 ManualVersionResponse 스키마 개선

**파일:** `app/schemas/manual.py` - 업데이트

```python
class ManualVersionResponse(BaseResponseSchema):
    """
    Manual version response (v2.1 개선)

    기존 /{manual_id}/versions와 새로운 /versions 쿼리 엔드포인트에서
    모두 사용 가능하도록 구조화
    """

    model_config = ConfigDict(populate_by_name=True)

    value: str = Field(alias="version", description="버전 번호 (예: v1.6)")
    label: str = Field(
        description="사용자 표시용 레이블 (버전 + 상태)"
    )
    date: str = Field(
        description="버전 생성/승인 날짜 (YYYY-MM-DD 형식)"
    )
    status: ManualStatus = Field(
        description="버전 상태 (APPROVED, DEPRECATED)"
    )
    manual_id: UUID = Field(
        description="이 버전의 메뉴얼 ID (비교 시 사용)"
    )

    # 예시:
    # {
    #   "value": "v1.5",
    #   "label": "v1.5 (DEPRECATED)",
    #   "date": "2024-12-01",
    #   "status": "DEPRECATED",
    #   "manual_id": "uuid-xxx"
    # }
```

#### 2.2.3 ManualService에 서비스 메서드 추가

**파일:** `app/services/manual_service.py` - 신규 메서드

```python
async def get_manual_versions_by_group(
    self,
    business_type: str,
    error_code: str,
    include_deprecated: bool = False,
) -> list[ManualVersionResponse]:
    """
    business_type + error_code로 메뉴얼 그룹의 버전 목록 조회

    **플로우:**
    1. 해당 그룹의 모든 APPROVED 메뉴얼 조회
    2. 필요 시 DEPRECATED도 포함
    3. ManualVersion으로 그룹화
    4. 최신순 정렬 후 반환

    **Returns:**
    최신순으로 정렬된 버전 목록
    """

    # Step 1: 해당 그룹의 메뉴얼 조회
    statuses = {ManualStatus.APPROVED}
    if include_deprecated:
        statuses.add(ManualStatus.DEPRECATED)

    manuals = await self.manual_repo.find_by_group(
        business_type=business_type,
        error_code=error_code,
        statuses=statuses,
    )

    if not manuals:
        raise RecordNotFoundError(
            f"No manual entries found for business_type={business_type}, "
            f"error_code={error_code}"
        )

    # Step 2: ManualVersion 기반으로 정보 구성
    responses: list[ManualVersionResponse] = []

    for manual in manuals:
        version = await self.version_repo.get_by_id(manual.version_id)
        if version is None:
            continue

        # 상태 표시 레이블
        if manual.status == ManualStatus.APPROVED:
            # 최신 APPROVED인지 확인
            latest = await self.manual_repo.find_latest_by_group(
                business_type=business_type,
                error_code=error_code,
                status=ManualStatus.APPROVED,
            )
            is_latest = latest and latest.id == manual.id
            label = f"{version.version} ({'현재 버전' if is_latest else 'APPROVED'})"
        else:
            label = f"{version.version} (DEPRECATED)"

        responses.append(
            ManualVersionResponse(
                value=version.version,
                version=version.version,  # alias 용
                label=label,
                date=version.created_at.strftime("%Y-%m-%d"),
                status=manual.status,
                manual_id=manual.id,
            )
        )

    # Step 3: 최신순 정렬 (created_at 기준)
    responses.sort(
        key=lambda x: x.date,
        reverse=True,
    )

    return responses
```

#### 2.2.4 ManualRepository에 쿼리 메서드 추가

**파일:** `app/repositories/manual_rdb.py` - 신규 메서드

```python
async def find_by_group(
    self,
    business_type: str,
    error_code: str,
    statuses: set[ManualStatus] | None = None,
) -> list[ManualEntry]:
    """
    같은 (business_type, error_code) 그룹의 메뉴얼 모두 조회

    **Parameters:**
    - business_type: 업무 구분
    - error_code: 에러 코드
    - statuses: 필터링할 상태 (None이면 모든 상태)

    **Returns:**
    created_at DESC 정렬 (최신순)
    """

    stmt = select(ManualEntry).where(
        (ManualEntry.business_type == business_type)
        & (ManualEntry.error_code == error_code)
    )

    if statuses:
        stmt = stmt.where(ManualEntry.status.in_(statuses))

    stmt = stmt.order_by(ManualEntry.created_at.desc())

    result = await self.session.execute(stmt)
    return list(result.scalars().all())


async def find_latest_by_group(
    self,
    business_type: str,
    error_code: str,
    status: ManualStatus | None = None,
    exclude_id: UUID | None = None,
) -> ManualEntry | None:
    """
    같은 (business_type, error_code) 그룹의 최신 메뉴얼 조회

    **Parameters:**
    - business_type: 업무 구분
    - error_code: 에러 코드
    - status: 상태 필터 (None이면 모든 상태)
    - exclude_id: 제외할 메뉴얼 ID

    **Returns:**
    최신 메뉴얼 (created_at 최신순)
    """

    stmt = select(ManualEntry).where(
        (ManualEntry.business_type == business_type)
        & (ManualEntry.error_code == error_code)
    )

    if status is not None:
        stmt = stmt.where(ManualEntry.status == status)

    if exclude_id is not None:
        stmt = stmt.where(ManualEntry.id != exclude_id)

    stmt = stmt.order_by(ManualEntry.created_at.desc()).limit(1)

    result = await self.session.execute(stmt)
    return result.scalar_one_or_none()
```

---

## Part 3: Gap 3 - ManualReviewTask.comparison_type 필드 추가

### 3.1 모델 변경

**파일:** `app/models/task.py` - 필드 추가

```python
from enum import Enum

class ComparisonType(str, Enum):
    """비교 타입 분류"""
    SIMILAR = "similar"         # ≥0.95 유사도
    SUPPLEMENT = "supplement"   # 0.7-0.95 유사도 (자동 병합)
    NEW = "new"                 # <0.7 유사도


class ManualReviewTask(BaseModel):
    """FR-4/FR-5/FR-6/FR-7: 메뉴얼 충돌 검출 및 승인/반려 워크플로우 태스크"""

    __tablename__ = "manual_review_tasks"

    # ... 기존 필드 ...

    # NEW: v2.1 추가 필드
    comparison_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="new",
        comment="비교 타입: similar/supplement/new",
    )

    # ... 나머지 필드 ...
```

### 3.2 Alembic 마이그레이션

**파일:** `alembic/versions/YYYYMMDD_hhmmss_add_comparison_type.py` (신규)

```python
"""Add comparison_type field to manual_review_tasks

Revision ID: add_comparison_type_20251211
Revises: <previous_revision>
Create Date: 2025-12-11 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_comparison_type_20251211"
down_revision = "<previous_revision>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add comparison_type column with default value"""

    # Step 1: nullable=True로 컬럼 추가
    op.add_column(
        "manual_review_tasks",
        sa.Column(
            "comparison_type",
            sa.String(20),
            nullable=True,
            comment="비교 타입: similar/supplement/new",
        ),
    )

    # Step 2: 기존 데이터에 default value "new" 적용
    op.execute(
        "UPDATE manual_review_tasks SET comparison_type = 'new' "
        "WHERE comparison_type IS NULL"
    )

    # Step 3: NOT NULL 제약 추가
    op.alter_column(
        "manual_review_tasks",
        "comparison_type",
        nullable=False,
    )


def downgrade() -> None:
    """Remove comparison_type column"""
    op.drop_column("manual_review_tasks", "comparison_type")
```

### 3.3 마이그레이션 실행

```bash
# 마이그레이션 생성 (자동)
uv run alembic revision --autogenerate -m "Add comparison_type to manual_review_tasks"

# 마이그레이션 적용
uv run alembic upgrade head
```

### 3.4 관련 코드 업데이트

**모든 `_create_review_task` 호출 사이트에서 comparison_type 전달:**

```python
# Before
await self._create_review_task(
    new_entry=manual_entry,
    reason="validation_failed",
)

# After
await self._create_review_task(
    new_entry=manual_entry,
    old_entry=existing_manual,
    comparison_type=ComparisonType.SUPPLEMENT,
    similarity_score=0.82,
    reason="validation_failed",
)
```

---

## Part 4: Gap 4 - VectorStore 메타데이터 필터링

### 4.1 현재 코드 상태

**파일:** `app/services/manual_service.py` (lines 269-273)

```python
query_text = self._build_manual_text(manual)
vector_results = await self.vectorstore.search(
    query=query_text,
    top_k=top_k,
)
```

**문제점:**
- 메타데이터 필터링 없음
- "인터넷뱅킹/E001" 메뉴얼이 "모바일뱅킹/E002" 메뉴얼과 비교될 수 있음

### 4.2 VectorStore Protocol 업데이트

**파일:** `app/vectorstore/protocol.py` - 확장

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass


@dataclass
class VectorSearchResult:
    """벡터 검색 결과"""
    id: str
    score: float
    metadata: dict[str, Any] | None = None


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """VectorStore 추상 프로토콜 (v2.1 개선)"""

    async def index(
        self,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,  # NEW
    ) -> None:
        """
        문서 인덱싱

        Args:
            document_id: 문서 ID
            text: 인덱싱할 텍스트
            metadata: 필터링용 메타데이터 (business_type, error_code 등)
        """
        ...

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filters: dict[str, Any] | None = None,  # NEW
    ) -> list[VectorSearchResult]:
        """
        의미론적 유사도로 검색

        Args:
            query: 검색 쿼리 텍스트
            top_k: 반환할 최대 결과 개수
            metadata_filters: 메타데이터 필터 (예: {"business_type": "인터넷뱅킹"})

        Returns:
            유사도 순으로 정렬된 결과
        """
        ...

    async def delete(
        self,
        document_id: str,
    ) -> None:
        """문서 삭제"""
        ...
```

### 4.3 구체적 구현 업데이트

#### 4.3.1 Manual 인덱싱 시 메타데이터 포함

**파일:** `app/services/manual_service.py` - `_index_manual_vector` 메서드

```python
async def _index_manual_vector(self, manual: ManualEntry) -> None:
    """
    메뉴얼을 VectorStore에 인덱싱 (메타데이터 포함)

    **메타데이터:**
    - business_type: 업무 구분
    - error_code: 에러 코드
    - status: 메뉴얼 상태 (APPROVED/DEPRECATED 등)
    """

    if self.vectorstore is None:
        return

    text = self._build_manual_text(manual)

    metadata = {
        "business_type": manual.business_type,
        "error_code": manual.error_code,
        "status": manual.status.value,
        "version_id": str(manual.version_id),
        "manual_id": str(manual.id),
    }

    await self.vectorstore.index(
        document_id=str(manual.id),
        text=text,
        metadata=metadata,  # NEW
    )
```

#### 4.3.2 ComparisonService에서 필터링된 검색

**파일:** `app/services/comparison_service.py` (이미 위에서 작성함)

```python
vector_results = await self.vectorstore.search(
    query=new_draft_text,
    top_k=1,
    metadata_filters={  # NEW: 메타데이터 필터링
        "business_type": new_draft.business_type,
        "error_code": new_draft.error_code,
        "status": "APPROVED",  # APPROVED만
    },
)
```

#### 4.3.3 MockVectorStore 구현 업데이트

**파일:** `app/vectorstore/mock.py`

```python
class MockVectorStore:
    """Mock VectorStore with metadata filtering support"""

    def __init__(self) -> None:
        # 메타데이터를 함께 저장
        self.documents: dict[str, tuple[str, dict[str, Any]]] = {}

    async def index(
        self,
        document_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """문서 인덱싱 (메타데이터 포함)"""
        self.documents[document_id] = (text, metadata or {})

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        """
        간단한 유사도 기반 검색 (데모용)
        실제로는 cosine similarity 계산
        """

        results: list[VectorSearchResult] = []

        for doc_id, (text, metadata) in self.documents.items():
            # 메타데이터 필터 확인
            if metadata_filters:
                matches = all(
                    metadata.get(key) == value
                    for key, value in metadata_filters.items()
                )
                if not matches:
                    continue  # 필터 조건 불일치 시 스킵

            # 간단한 유사도 계산 (단어 겹침 기반)
            score = self._simple_similarity(query, text)
            if score > 0:
                results.append(
                    VectorSearchResult(
                        id=doc_id,
                        score=score,
                        metadata=metadata,
                    )
                )

        # top_k 개만 반환 (유사도 순)
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _simple_similarity(self, query: str, text: str) -> float:
        """간단한 유사도 계산"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words or not text_words:
            return 0.0

        overlap = len(query_words & text_words)
        union = len(query_words | text_words)
        return overlap / union if union > 0 else 0.0
```

#### 4.3.4 check_conflict_and_create_task 업데이트

**파일:** `app/services/manual_service.py` (기존 메서드 업데이트)

```python
async def check_conflict_and_create_task(
    self,
    manual_id: UUID,
    *,
    top_k: int = 3,
    similarity_threshold: float = 0.85,
) -> ManualReviewTaskResponse | None:
    """FR-6: 신규 초안과 기존 메뉴얼 자동 비교 후 리뷰 태스크 생성"""

    manual = await self.manual_repo.get_by_id(manual_id)
    if manual is None:
        raise RecordNotFoundError(...)
    if manual.status != ManualStatus.DRAFT:
        return None
    if self.vectorstore is None:
        logger.warning(...)
        return None

    query_text = self._build_manual_text(manual)

    # NEW: 메타데이터 필터링 추가
    vector_results = await self.vectorstore.search(
        query=query_text,
        top_k=top_k,
        metadata_filters={
            "business_type": manual.business_type,
            "error_code": manual.error_code,
            "status": "APPROVED",
        },
    )

    # 나머지 코드는 동일...
```

---

## Part 5: 통합 구현 로드맵

### 5.1 Phase 0: 준비 작업 (1일)

- [ ] ComparisonType enum 정의 (schemas + models에서 일관성 유지)
- [ ] Alembic migration 파일 생성
- [ ] VectorStoreProtocol 업데이트

### 5.2 Phase 1: 핵심 서비스 (2-3일)

- [ ] ComparisonService 구현 및 테스트
- [ ] ManualService 개선 (create_draft_from_consultation 통합)
- [ ] _create_review_task 확장 (comparison_type 포함)
- [ ] 기존 check_conflict_and_create_task 메타데이터 필터링 추가

### 5.3 Phase 2: API 엔드포인트 (1-2일)

- [ ] POST /manuals/draft 업데이트 (응답 스키마 변경)
- [ ] GET /manuals/versions?business_type=&error_code= 신규 엔드포인트
- [ ] ManualVersionResponse 개선
- [ ] 라우터 등록 순서 조정 (/versions 더 구체적이므로 /{manual_id}/versions 전에)

### 5.4 Phase 3: 저장소 계층 (1일)

- [ ] ManualRepository에 find_by_group, find_latest_by_group 메서드 추가
- [ ] VectorStore 구현들 업데이트 (metadata_filters 지원)

### 5.5 Phase 4: 마이그레이션 및 테스트 (2-3일)

- [ ] Alembic migration 실행
- [ ] Unit 테스트 작성 (ComparisonService)
- [ ] Integration 테스트 (전체 플로우)
- [ ] E2E 테스트 (API 엔드포인트)

### 5.6 Phase 5: 문서화 (1일)

- [ ] API 문서 업데이트
- [ ] 마이그레이션 가이드
- [ ] 개발자 문서

---

## Part 6: 테스트 계획

### 6.1 Unit Tests - ComparisonService

```python
# tests/unit/test_comparison_service.py

@pytest.mark.asyncio
async def test_compare_similar():
    """유사도 ≥0.95 → SIMILAR"""
    service = ComparisonService(session=mock_session, vectorstore=mock_vs)
    mock_vs.search.return_value = [
        VectorSearchResult(id="existing", score=0.97)
    ]

    result = await service.compare(new_draft, None)
    assert result.comparison_type == ComparisonType.SIMILAR
    assert result.similarity_score == 0.97


@pytest.mark.asyncio
async def test_compare_supplement():
    """유사도 0.7-0.95 → SUPPLEMENT"""
    # ...


@pytest.mark.asyncio
async def test_compare_new():
    """유사도 <0.7 → NEW"""
    # ...


@pytest.mark.asyncio
async def test_compare_with_user_selected_version():
    """사용자가 compare_with_manual_id 지정 → 해당 메뉴얼과 비교"""
    # ...


@pytest.mark.asyncio
async def test_compare_metadata_filtering():
    """다른 그룹(business_type/error_code)은 검색에서 제외"""
    # ...


@pytest.mark.asyncio
async def test_compare_vectorstore_unavailable():
    """VectorStore 에러 → NEW로 안전 처리"""
    # ...
```

### 6.2 Integration Tests - ManualService

```python
# tests/integration/test_manual_service_v2_1.py

@pytest.mark.asyncio
async def test_create_draft_similar_flow():
    """SIMILAR 경로: 기존 메뉴얼 반환"""
    # 상담 생성 → draft 생성 → SIMILAR 판정 → 응답 검증


@pytest.mark.asyncio
async def test_create_draft_supplement_flow():
    """SUPPLEMENT 경로: 자동 병합 + 태스크 생성"""
    # ...


@pytest.mark.asyncio
async def test_create_draft_new_flow():
    """NEW 경로: 신규 초안 + 태스크 생성"""
    # ...


@pytest.mark.asyncio
async def test_get_manual_versions_by_group():
    """GET /manuals/versions?business_type=&error_code="""
    # ...
```

### 6.3 API Tests (E2E)

```python
# tests/e2e/test_manual_api_v2_1.py

async def test_create_draft_api_similar():
    """POST /manuals/draft - SIMILAR 응답"""
    response = await client.post(
        "/api/v1/manuals/draft",
        json={
            "consultation_id": "uuid-xxx",
            "enforce_hallucination_check": True,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["comparison_type"] == "similar"
    assert "existing_manual" in data
    assert "review_task_id" not in data


async def test_list_versions_by_group():
    """GET /manuals/versions?business_type=&error_code="""
    response = await client.get(
        "/api/v1/manuals/versions",
        params={
            "business_type": "인터넷뱅킹",
            "error_code": "E001",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert "value" in data[0]
    assert "label" in data[0]
    assert data[0]["value"] == "v1.6"  # 최신순
```

---

## Part 7: 마이그레이션 체크리스트

### 기존 데이터 호환성

```
Before (현재):
- ManualReviewTask:
  - old_entry_id, new_entry_id, similarity, status
  - comparison_type 필드 없음

After (v2.1):
- ManualReviewTask:
  - old_entry_id, new_entry_id, similarity, status
  - + comparison_type (NOT NULL, default='new')

Migration Strategy:
1. ALTER TABLE: comparison_type VARCHAR(20) NULL 추가
2. UPDATE: 기존 행 comparison_type = 'new'로 설정
3. ALTER TABLE: comparison_type NOT NULL로 변경
```

### 검증 계획

```sql
-- Migration 후 검증
SELECT COUNT(*) as total,
       COUNT(CASE WHEN comparison_type IS NULL THEN 1 END) as null_count
FROM manual_review_tasks;
-- Expected: null_count = 0

-- 데이터 분포 확인
SELECT comparison_type, COUNT(*)
FROM manual_review_tasks
GROUP BY comparison_type;
-- Expected: all rows have comparison_type='new' (initially)
```

---

## Part 8: 배포 전 체크리스트

- [ ] 모든 unit/integration/E2E 테스트 통과
- [ ] Alembic migration 테스트 및 검증
- [ ] 기존 API 호환성 확인 (breaking changes 없음)
- [ ] 성능 테스트 (VectorStore 메타데이터 필터링)
- [ ] 코드 리뷰 및 타입 체크 (`mypy`)
- [ ] 문서 업데이트 완료
- [ ] 롤백 계획 수립

---

## 요약

이 설계 문서는 v2.1 스펙과 실제 구현 간의 3가지 핵심 갭을 해결합니다:

| 갭 | 해결책 | 파일 |
|-----|-------|------|
| **Gap 1** | ComparisonService 구현 + create_draft_from_consultation 통합 + 3-path 응답 | `app/services/comparison_service.py`, `app/services/manual_service.py` |
| **Gap 2** | GET /manuals/versions?business_type=&error_code= 엔드포인트 + 저장소 메서드 | `app/routers/manuals.py`, `app/repositories/manual_rdb.py` |
| **Gap 3** | ManualReviewTask.comparison_type 필드 추가 + Alembic migration | `app/models/task.py`, `alembic/versions/...py` |
| **Gap 4** | VectorStore 메타데이터 필터링 + Protocol 업데이트 | `app/vectorstore/protocol.py`, `app/services/comparison_service.py` |

**Next Steps:**
1. 이 설계 문서 검토 및 승인
2. Phase 0 준비 작업 시작
3. Phase 1-5 순차적 구현
4. 철저한 테스트 및 검증
5. 배포 전 체크리스트 확인 후 배포

