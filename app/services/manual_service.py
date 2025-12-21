"""
Manual Service (FR-2/FR-9 1차 구현)

상담을 기반으로 메뉴얼 초안을 생성하고, 환각 검증에 실패하면 리뷰 태스크를 생성한다.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4
import time
import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthorizationError,
    RecordNotFoundError,
    ValidationError,
    BusinessLogicError,
    NeedsReReviewError,
)
from app.core.logging import get_logger, log_llm_call, measure_latency, metrics_counter
from app.llm.protocol import LLMClientProtocol
from app.llm.prompts.manual_draft import (
    build_manual_draft_prompt,
    SYSTEM_PROMPT,
)
from app.llm.prompts.manual_compare import (
    build_manual_compare_prompt,
    SYSTEM_PROMPT as COMPARE_SYSTEM_PROMPT,
)
from app.llm.prompts.manual_diff import (
    build_manual_diff_summary_prompt,
    SYSTEM_PROMPT as DIFF_SYSTEM_PROMPT,
)
from app.models.consultation import Consultation
from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.models.task import ManualReviewTask, TaskStatus, ComparisonType
from app.models.user import User, UserRole
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.manual_rdb import (
    ManualEntryRDBRepository,
    ManualReviewTaskRepository,
    ManualVersionRepository,
)
from app.repositories.common_code_rdb import CommonCodeItemRepository
from app.schemas.manual import (
    ManualDraftCreateFromConsultationRequest,
    ManualDraftResponse,
    ManualDraftCreateResponse,
    ManualApproveRequest,
    ManualVersionInfo,
    ManualReviewTaskResponse,
    ManualSearchResult,
    ManualSearchParams,
    ManualEntryResponse,
    ManualEntryUpdate,
    ManualVersionResponse,
    ManualVersionDiffResponse,
    ManualDiffEntrySnapshot,
    ManualModifiedEntry,
    BusinessType,
    ManualGuidelineItem,
    ManualDetailResponse,
    ComparisonType,
)
from app.vectorstore.protocol import VectorStoreProtocol
from app.services.rerank import rerank_results
from app.services.validation import (
    validate_keywords_in_source,
    validate_sentences_subset_of_source,
)
from app.services.comparison_service import ComparisonService
from app.core.config import settings
from app.core.permissions import filter_tasks_for_user, get_user_department_ids
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


def parse_guideline_string(guideline_text: str) -> list[dict[str, str]]:
    """
    guideline 문자열을 파싱하여 제목/설명 배열로 변환.

    포맷: "제목1\\n설명1\\n제목2\\n설명2" 또는 각 라인이 제목/설명 쌍으로 구성
    """
    if not guideline_text or not guideline_text.strip():
        return []

    lines = [line.strip() for line in guideline_text.split("\n") if line.strip()]

    guidelines: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines):
            # 제목과 설명이 한 쌍
            title = lines[i]
            description = lines[i + 1]
            guidelines.append({"title": title, "description": description})
            i += 2
        else:
            # 남은 것이 제목만 있으면 설명은 공백
            guidelines.append({"title": lines[i], "description": ""})
            i += 1

    return guidelines


class ManualService:
    """메뉴얼 관련 비즈니스 로직을 담당하는 서비스."""

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
        comparison_service: ComparisonService | None = None,
        user_repo: UserRepository | None = None,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.vectorstore = vectorstore
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)
        self.review_repo = review_repo or ManualReviewTaskRepository(session)
        self.version_repo = version_repo or ManualVersionRepository(session)
        self.consultation_repo = consultation_repo or ConsultationRepository(session)
        self.common_code_item_repo = common_code_item_repo or CommonCodeItemRepository(session)
        self._comparison_service = comparison_service
        self.user_repo = user_repo or UserRepository(session)

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
           - SIMILAR: 기존 메뉴얼 반환, 초안 ARCHIVED로 표시
           - SUPPLEMENT: LLM으로 자동 병합, 리뷰 태스크 생성
           - NEW: 그대로 초안 유지, 리뷰 태스크 생성
        """

        # Step 1: 상담 조회
        consultation = await self.consultation_repo.get_by_id(request.consultation_id)
        if consultation is None:
            raise RecordNotFoundError(f"Consultation(id={request.consultation_id}) not found")

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
        )

        # Step 5: ComparisonService로 비교
        comparison_result = await self.comparison_service.compare(
            new_draft=manual_entry,
            compare_with_manual_id=request.compare_with_manual_id,
        )

        # business_type 공통코드 매핑 조회 (한 번만)
        business_type_items = await self.common_code_item_repo.get_by_group_code(
            "BUSINESS_TYPE", is_active_only=True
        )
        business_type_map = {
            item.code_key: item.code_value for item in business_type_items
        }

        # Step 6: comparison_type에 따른 분기 처리
        response: ManualDraftCreateResponse
        if comparison_result.comparison_type == ComparisonType.SIMILAR:
            # SIMILAR 경로: 기존 메뉴얼 반환, draft는 ARCHIVED로 표시
            manual_entry.status = ManualStatus.ARCHIVED
            await self.manual_repo.update(manual_entry)

            draft_response = await self._enrich_manual_entry_response(
                manual_entry, business_type_map
            )
            existing_response = await self._enrich_manual_entry_response(
                comparison_result.existing_manual, business_type_map
            )

            response = ManualDraftCreateResponse(
                comparison_type=ComparisonType.SIMILAR,
                id=manual_entry.id,
                created_at=manual_entry.created_at,
                updated_at=manual_entry.updated_at,
                draft_entry=draft_response,
                existing_manual=existing_response,
                similarity_score=comparison_result.similarity_score,
                comparison_version=comparison_result.compare_version,
                message=(
                    f"기존 메뉴얼(버전 {comparison_result.existing_manual.version_id})과 "
                    f"{comparison_result.similarity_score * 100:.0f}% 유사합니다. "
                    "기존 메뉴얼을 참고하세요."
                ),
            )

        elif comparison_result.comparison_type == ComparisonType.SUPPLEMENT:
            # SUPPLEMENT 경로: 자동 병합 + 리뷰 태스크
            review_task = await self._create_review_task(
                consultation=consultation,
                new_entry=manual_entry,
                old_entry=comparison_result.existing_manual,
                comparison_type=ComparisonType.SUPPLEMENT,
                similarity_score=comparison_result.similarity_score,
                compare_version=comparison_result.compare_version,
                reason=comparison_result.reason,
                auto_merged=True,
            )

            draft_response = await self._enrich_manual_entry_response(
                manual_entry, business_type_map
            )
            existing_response = await self._enrich_manual_entry_response(
                comparison_result.existing_manual, business_type_map
            )

            response = ManualDraftCreateResponse(
                comparison_type=ComparisonType.SUPPLEMENT,
                id=manual_entry.id,
                created_at=manual_entry.created_at,
                updated_at=manual_entry.updated_at,
                draft_entry=draft_response,
                existing_manual=existing_response,
                review_task_id=review_task.id,
                similarity_score=comparison_result.similarity_score,
                comparison_version=comparison_result.compare_version,
                message=(
                    f"기존 메뉴얼(버전 {comparison_result.existing_manual.version_id})의 "
                    f"내용을 보충했습니다. 검토자가 확인 후 승인합니다."
                ),
            )

        else:  # ComparisonType.NEW
            # NEW 경로: 신규 draft, 리뷰 태스크 생성
            review_task = await self._create_review_task(
                consultation=consultation,
                new_entry=manual_entry,
                old_entry=None,
                comparison_type=ComparisonType.NEW,
                similarity_score=None,
                compare_version=comparison_result.compare_version,
                reason=comparison_result.reason,
                auto_merged=False,
            )

            draft_response = await self._enrich_manual_entry_response(
                manual_entry, business_type_map
            )

            response = ManualDraftCreateResponse(
                comparison_type=ComparisonType.NEW,
                id=manual_entry.id,
                created_at=manual_entry.created_at,
                updated_at=manual_entry.updated_at,
                draft_entry=draft_response,
                existing_manual=None,
                review_task_id=review_task.id,
                similarity_score=None,
                comparison_version=comparison_result.compare_version,
                message="신규 메뉴얼 초안으로 생성되었습니다.",
            )

        await self._mark_consultation_manual_generated(consultation)
        return response

    async def _mark_consultation_manual_generated(self, consultation: Consultation) -> None:
        """정상 종료 시 상담에 플래그와 타임스탬프를 기록."""

        consultation.is_manual_generated = True
        consultation.manual_generated_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def get_manual(self, manual_id: UUID) -> ManualEntryResponse:
        """메뉴얼 단건 상세 조회."""

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        response = ManualEntryResponse.model_validate(manual)
        
        # business_type_name 조회 및 추가
        if manual.business_type:
            business_type_items = await self.common_code_item_repo.get_by_group_code(
                "BUSINESS_TYPE", is_active_only=True
            )
            business_type_map = {
                item.code_key: item.code_value for item in business_type_items
            }
            response = response.model_copy(
                update={
                    "business_type_name": business_type_map.get(manual.business_type)
                }
            )
        
        return response

    async def get_manual_by_version(
        self, manual_id: UUID, version: str
    ) -> ManualDetailResponse:
        """FR-14: 특정 버전의 메뉴얼 상세 조회.

        guideline 필드를 문자열에서 배열로 변환하여 반환한다.

        Args:
            manual_id: 메뉴얼 ID (현재는 사용되지 않음 - 단일 그룹 가정)
            version: 버전 번호 (예: "v2.1")

        Returns:
            ManualDetailResponse: 메뉴얼 상세 정보 (guidelines는 배열)

        Raises:
            RecordNotFoundError: 버전을 찾을 수 없는 경우
        """

        # 버전 조회
        manual_version = await self.version_repo.get_by_version(version)
        if manual_version is None:
            raise RecordNotFoundError(f"Manual version '{version}' not found")

        # 해당 버전의 메뉴얼 항목 조회 (APPROVED 상태만)
        entries = list(
            await self.manual_repo.find_by_version(
                manual_version.id,
                statuses={ManualStatus.APPROVED},
            )
        )

        if not entries:
            raise RecordNotFoundError(
                f"No approved manual entries found for version '{version}'"
            )

        # 임시 구현: 첫 번째 엔트리 반환 (실제로는 manual_id로 필터링해야 함)
        # TODO: manual_id를 기반으로 특정 항목만 반환하도록 수정
        entry = entries[0]

        # guideline 파싱
        guidelines = parse_guideline_string(entry.guideline)

        return ManualDetailResponse(
            id=entry.id,
            manual_id=entry.id,
            version=manual_version.version,
            topic=entry.topic,
            keywords=entry.keywords or [],
            background=entry.background,
            guidelines=[
                ManualGuidelineItem(title=g["title"], description=g["description"])
                for g in guidelines
            ],
            status=entry.status,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )

    async def check_conflict_and_create_task(
        self,
        manual_id: UUID,
        *,
        top_k: int = 3,
        similarity_threshold: float = 0.85,
    ) -> ManualReviewTaskResponse | None:
        """FR-6: 신규 초안과 기존 메뉴얼 자동 비교 후 리뷰 태스크 생성."""

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")
        if manual.status != ManualStatus.DRAFT:
            return None
        if self.vectorstore is None:
            logger.warning(
                "manual_vectorstore_not_configured_skip_conflict", manual_id=str(manual.id)
            )
            return None

        query_text = self._build_manual_text(manual)
        vector_results = await self.vectorstore.search(
            query=query_text,
            top_k=top_k,
            metadata_filter={
                "business_type": manual.business_type,
                "error_code": manual.error_code,
                "status": "APPROVED",
            },
        )

        candidate_ids = [
            res.id
            for res in vector_results
            if res.score >= similarity_threshold and res.id != manual.id
        ]
        if not candidate_ids:
            return None

        candidates = await self.manual_repo.find_by_ids(candidate_ids)
        approved_candidates = [c for c in candidates if c.status == ManualStatus.APPROVED]
        if not approved_candidates:
            return None

        # 점수순 정렬 (VectorStore 결과 순서 유지)
        candidate_map = {c.id: c for c in approved_candidates}
        chosen = None
        chosen_score = None
        for res in vector_results:
            if res.id in candidate_map:
                chosen = candidate_map[res.id]
                chosen_score = res.score
                break

        if chosen is None or chosen_score is None:
            return None

        diff_json, diff_text = await self._call_llm_compare(chosen, manual)

        task = ManualReviewTask(
            old_entry_id=chosen.id,
            new_entry_id=manual.id,
            similarity=chosen_score,
            status=TaskStatus.TODO,
            decision_reason="auto_conflict_detected",
        )
        await self.review_repo.create(task)

        return ManualReviewTaskResponse(
            id=task.id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            old_entry_id=task.old_entry_id,
            new_entry_id=task.new_entry_id,
            similarity=task.similarity,
            status=task.status,
            reviewer_id=task.reviewer_id,
            review_notes=task.review_notes,
            old_manual_summary=self._summarize_manual(chosen),
            new_manual_summary=self._summarize_manual(manual),
            diff_text=diff_text,
            diff_json=diff_json,
            business_type=self._resolve_business_type(manual),
            new_manual_topic=manual.topic,
            new_manual_keywords=manual.keywords,
        )

    async def approve_manual(
        self,
        manual_id: UUID,
        request: ManualApproveRequest,
    ) -> ManualVersionInfo:
        """
        FR-4/FR-5: 메뉴얼 승인 (리뷰 태스크 기반 가드 + 대체 관계 기록)
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        review_task = await self.review_repo.get_latest_by_manual_id(manual_id)
        if review_task is None:
            raise BusinessLogicError("Review task not found for manual draft")

        logger.info(
            "manual_approve_start",
            manual_id=str(manual_id),
            approver_id=str(request.approver_id),
            comparison_type=review_task.comparison_type.value,
            compared_with_manual_id=str(review_task.old_entry_id) if review_task.old_entry_id else None,
        )

        if review_task.comparison_type in {ComparisonType.SIMILAR, ComparisonType.SUPPLEMENT}:
            guard_candidate = await self.comparison_service.find_best_match_candidate(manual)
            if guard_candidate and guard_candidate.id != review_task.old_entry_id:
                raise NeedsReReviewError(
                    "approved candidate changed after draft; please re-run review"
                )

        latest_version = await self.version_repo.get_latest_version(
            business_type=manual.business_type,
            error_code=manual.error_code,
        )
        next_version_num = self._next_version_number(latest_version)

        next_version = ManualVersion(
            version=str(next_version_num),
            business_type=manual.business_type,
            error_code=manual.error_code,
        )
        await self.version_repo.create(next_version)

        if review_task.comparison_type in {ComparisonType.SIMILAR, ComparisonType.SUPPLEMENT}:
            if review_task.old_entry_id:
                await self._apply_replacement(
                    new_manual=manual,
                    old_manual_id=review_task.old_entry_id,
                    comparison_type=review_task.comparison_type,
                    similarity_score=review_task.similarity_score,
                    approver_id=request.approver_id,
                )

        manual.status = ManualStatus.APPROVED
        manual.version_id = next_version.id
        await self.manual_repo.update(manual)

        review_task.status = TaskStatus.DONE
        review_task.reviewer_id = review_task.reviewer_id or request.approver_id
        await self.review_repo.update(review_task)

        await self._index_manual_vector(manual)

        return ManualVersionInfo(
            version=next_version.version,
            approved_at=next_version.created_at,
        )

    async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
        """
        FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시 포함)
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        group_versions = list(
            await self.version_repo.list_versions(
                business_type=manual.business_type,
                error_code=manual.error_code,
            )
        )

        if not group_versions:
            return []

        # Ensure consistent sorting: most recent first
        group_versions.sort(
            key=lambda v: (v.created_at, v.id),
            reverse=True,
        )

        result: list[ManualVersionResponse] = []
        for idx, v in enumerate(group_versions):
            label = f"{v.version} (현재 버전)" if idx == 0 else v.version
            date_str = v.created_at.strftime("%Y-%m-%d")
            result.append(
                ManualVersionResponse(
                    version=v.version,
                    label=label,
                    date=date_str,
                    id=v.id,
                    created_at=v.created_at,
                    updated_at=v.updated_at,
                )
            )

        return result

    async def list_manuals(
        self,
        *,
        status: ManualStatus | None = None,
        limit: int = 100,
        employee_id: str | None = None,
    ) -> list[ManualEntryResponse]:
        """RFP FR-8/General: 메뉴얼 목록 조회"""

        statuses = {status} if status is not None else None
        entries = await self.manual_repo.list_entries(
            statuses=statuses,
            limit=limit,
            employee_id=employee_id,
        )
        
        # business_type 공통코드 매핑 조회 (한 번만)
        business_type_items = await self.common_code_item_repo.get_by_group_code(
            "BUSINESS_TYPE", is_active_only=True
        )
        business_type_map = {
            item.code_key: item.code_value for item in business_type_items
        }
        
        # 각 entry를 응답으로 변환하고 business_type_name 추가
        responses = []
        for entry in entries:
            response = ManualEntryResponse.model_validate(entry)
            response = response.model_copy(
                update={
                    "business_type_name": business_type_map.get(entry.business_type)
                }
            )
            responses.append(response)
        
        return responses

    async def get_approved_group_by_manual_id(
        self, manual_id: UUID
    ) -> list[ManualEntryResponse]:
        """
        해당 manual_id와 같은 business_type/error_code를 갖고 있는 APPROVED 항목 목록을 반환.
        동일 그룹 내 APPROVED 메뉴얼만 조회하며 business_type_name을 붙여서 반환.
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        if not manual.business_type or not manual.error_code:
            raise BusinessLogicError(
                f"ManualEntry(id={manual_id}) has no business_type or error_code"
            )

        entries = await self.manual_repo.find_all_approved_by_group(
            business_type=manual.business_type,
            error_code=manual.error_code,
        )

        business_type_items = await self.common_code_item_repo.get_by_group_code(
            "BUSINESS_TYPE", is_active_only=True
        )
        business_type_map = {
            item.code_key: item.code_value for item in business_type_items
        }

        responses: list[ManualEntryResponse] = []
        for entry in entries:
            response = await self._enrich_manual_entry_response(
                entry, business_type_map=business_type_map
            )
            responses.append(response)

        return responses

    async def get_manual_versions_by_group(
        self,
        business_type: str,
        error_code: str,
        include_deprecated: bool = False,
    ) -> list[ManualVersionResponse]:
        """
        FR-11(v2.1): business_type + error_code로 메뉴얼 그룹의 버전 목록 조회

        **용도:**
        - 초안 작성 전: UI에서 과거 버전 목록 표시
        - 사용자가 특정 버전과 비교하고 싶을 때 선택

        **Parameters:**
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
            "status": "DEPRECATED",
            "manual_id": "uuid-xxx"
          },
          {
            "value": "v1.6",
            "label": "v1.6 (현재 버전)",
            "date": "2024-12-05",
            "status": "APPROVED",
            "manual_id": "uuid-yyy"
          }
        ]
        ```
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
                    id=version.id,
                    created_at=version.created_at,
                    updated_at=version.updated_at,
                )
            )

        # Step 3: 최신순 정렬 (created_at 기준)
        responses.sort(
            key=lambda x: x.date,
            reverse=True,
        )

        return responses

    async def diff_versions(
        self,
        manual_id: UUID,
        *,
        base_version: str | None,
        compare_version: str | None,
        summarize: bool = False,
    ) -> ManualVersionDiffResponse:
        """
        FR-14: 버전 간 Diff (그룹별)
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        base, compare = await self._resolve_versions_for_diff(
            business_type=manual.business_type,
            error_code=manual.error_code,
            base_version=base_version,
            compare_version=compare_version,
        )
        if compare is None:
            raise RecordNotFoundError("비교할 버전을 찾을 수 없습니다.")

        base_entries = (
            list(
                await self.manual_repo.find_by_version(
                    base.id,
                    statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},
                )
            )
            if base is not None
            else []
        )
        compare_entries = list(
            await self.manual_repo.find_by_version(
                compare.id,
                statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},
            )
        )

        diff = self._calculate_diff(base_entries, compare_entries)
        summary = (
            await self._summarize_diff(
                diff,
                base_version=base.version if base else None,
                compare_version=compare.version,
            )
            if summarize
            else None
        )

        return ManualVersionDiffResponse(
            base_version=base.version if base else None,
            compare_version=compare.version,
            added_entries=diff["added_entries"],
            removed_entries=diff["removed_entries"],
            modified_entries=diff["modified_entries"],
            llm_summary=summary,
        )

    async def diff_draft_with_active(
        self,
        draft_id: UUID,
        *,
        summarize: bool = False,
    ) -> ManualVersionDiffResponse:
        """FR-14 시나리오 C: 운영 버전 vs 특정 DRAFT 세트 비교."""

        draft_entry = await self.manual_repo.get_by_id(draft_id)
        if draft_entry is None:
            raise RecordNotFoundError(f"Draft manual(id={draft_id}) not found")
        if draft_entry.status != ManualStatus.DRAFT:
            raise BusinessLogicError("draft_id는 DRAFT 상태 메뉴얼이어야 합니다.")

        active_version = await self.version_repo.get_latest_version()
        if active_version is None:
            raise RecordNotFoundError("활성화된 APPROVED 버전이 없습니다.")

        base_entries = list(
            await self.manual_repo.find_by_version(
                active_version.id,
                statuses={ManualStatus.APPROVED},
            )
        )
        related_drafts = await self.manual_repo.find_by_consultation_id(
            draft_entry.source_consultation_id
        )
        draft_entries = [e for e in related_drafts if e.status == ManualStatus.DRAFT]
        if not draft_entries:
            draft_entries = [draft_entry]

        compare_entries = self._apply_drafts_to_base(base_entries, draft_entries)
        diff = self._calculate_diff(base_entries, compare_entries)

        summary = (
            await self._summarize_diff(
                diff,
                base_version=active_version.version,
                compare_version="DRAFT",
            )
            if summarize
            else None
        )

        return ManualVersionDiffResponse(
            base_version=active_version.version,
            compare_version="DRAFT",
            added_entries=diff["added_entries"],
            removed_entries=diff["removed_entries"],
            modified_entries=diff["modified_entries"],
            llm_summary=summary,
        )

    async def _call_llm_for_draft(
        self,
        *,
        inquiry_text: str,
        action_taken: str,
        business_type: str | None,
        error_code: str | None,
    ) -> dict[str, Any]:
        """LLM 호출 Stub. 실제 API 연동은 LLMClientProtocol 구현체가 담당."""

        prompt = build_manual_draft_prompt(
            inquiry_text=inquiry_text,
            action_taken=action_taken,
            business_type=business_type,
            error_code=error_code,
        )
        start = time.perf_counter()
        try:
            response = await self.llm_client.complete_json(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.0,
            )
            return response
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            log_llm_call(
                operation="manual_draft",
                model=getattr(self.llm_client, "model", None),
                latency_ms=latency_ms,
                tokens=None,
            )

    def _detect_hallucination(self, keywords: list[str], source_text: str) -> bool:
        """모든 키워드가 원문에 존재하는지 검증 (간단한 환각 방지 규칙)."""

        lowered = source_text.lower()
        for keyword in keywords:
            if keyword.lower() not in lowered:
                logger.warning("hallucination_detected_keyword_absent", keyword=keyword)
                return True
        return False

    async def _persist_manual_entry(
        self,
        *,
        consultation_id: UUID,
        llm_payload: dict[str, Any],
        business_type: str | None,
        error_code: str | None,
    ) -> ManualEntry:
        manual_entry = ManualEntry(
            keywords=llm_payload.get("keywords", []),
            topic=llm_payload.get("topic", ""),
            background=llm_payload.get("background", ""),
            guideline=llm_payload.get("guideline", ""),
            business_type=llm_payload.get("business_type") or business_type,
            error_code=llm_payload.get("error_code") or error_code,
            source_consultation_id=consultation_id,
            status=ManualStatus.DRAFT,
        )
        if manual_entry.id is None:
            manual_entry.id = uuid4()
        now = datetime.now(timezone.utc)
        manual_entry.created_at = now
        manual_entry.updated_at = now
        saved_manual = await self.manual_repo.create(manual_entry)
        return saved_manual if saved_manual is not None else manual_entry

    async def _call_llm_compare(
        self, old: ManualEntry, new: ManualEntry
    ) -> tuple[dict[str, Any] | None, str | None]:
        """LLM 비교 호출 (Stub). 환각 방지 규칙은 Prompt에 명시."""

        prompt = build_manual_compare_prompt(
            old_manual=self._build_manual_text(old),
            new_manual=self._build_manual_text(new),
        )
        start = time.perf_counter()
        try:
            result = await self.llm_client.complete_json(
                prompt=prompt,
                system_prompt=COMPARE_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("manual_compare_llm_failed", error=str(exc))
            log_llm_call(
                operation="manual_compare",
                model=getattr(self.llm_client, "model", None),
                latency_ms=(time.perf_counter() - start) * 1000,
                tokens=None,
                error=str(exc),
            )
            return None, None

        latency_ms = (time.perf_counter() - start) * 1000
        log_llm_call(
            operation="manual_compare",
            model=getattr(self.llm_client, "model", None),
            latency_ms=latency_ms,
            tokens=None,
        )

        diff_text = None
        if isinstance(result, dict):
            if "differences" in result:
                diff_text = " | ".join(result.get("differences", []))
            else:
                diff_text = str(result)
        return result if isinstance(result, dict) else None, diff_text

    async def _summarize_diff(
        self,
        diff: dict[str, list[Any]],
        *,
        base_version: str | None,
        compare_version: str,
    ) -> str | None:
        """Diff JSON을 LLM을 통해 자연어 요약 (환각 방지 프롬프트 사용)."""

        payload = {
            "base_version": base_version,
            "compare_version": compare_version,
            "added_entries": [entry.model_dump() for entry in diff["added_entries"]],
            "removed_entries": [entry.model_dump() for entry in diff["removed_entries"]],
            "modified_entries": [entry.model_dump() for entry in diff["modified_entries"]],
        }
        prompt = build_manual_diff_summary_prompt(diff_json=json.dumps(payload, ensure_ascii=False))
        start = time.perf_counter()
        try:
            response = await self.llm_client.complete(
                prompt=prompt,
                system_prompt=DIFF_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=400,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            log_llm_call(
                operation="manual_diff_summary",
                model=getattr(self.llm_client, "model", None),
                latency_ms=latency_ms,
                tokens=None,
            )
            return response.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("manual_diff_summary_failed", error=str(exc))
            latency_ms = (time.perf_counter() - start) * 1000
            log_llm_call(
                operation="manual_diff_summary",
                model=getattr(self.llm_client, "model", None),
                latency_ms=latency_ms,
                tokens=None,
                error=str(exc),
            )
            return None

    def _calculate_diff(
        self,
        base_entries: list[ManualEntry],
        compare_entries: list[ManualEntry],
    ) -> dict[str, list[Any]]:
        """ManualEntry 목록을 비교해 added/removed/modified를 구한다."""

        base_map = {self._logical_key(entry): entry for entry in base_entries}
        compare_map = {self._logical_key(entry): entry for entry in compare_entries}

        added_entries = [
            self._to_snapshot(entry, logical_key=key)
            for key, entry in compare_map.items()
            if key not in base_map
        ]

        removed_entries = [
            self._to_snapshot(entry, logical_key=key)
            for key, entry in base_map.items()
            if key not in compare_map
        ]

        modified_entries: list[ManualModifiedEntry] = []
        for key, entry in compare_map.items():
            if key not in base_map:
                continue
            changed_fields = self._diff_fields(base_map[key], entry)
            if changed_fields:
                modified_entries.append(
                    ManualModifiedEntry(
                        logical_key=key,
                        before=self._to_snapshot(base_map[key], logical_key=key),
                        after=self._to_snapshot(entry, logical_key=key),
                        changed_fields=changed_fields,
                    )
                )

        return {
            "added_entries": added_entries,
            "removed_entries": removed_entries,
            "modified_entries": modified_entries,
        }

    def _apply_drafts_to_base(
        self,
        base_entries: list[ManualEntry],
        draft_entries: list[ManualEntry],
    ) -> list[ManualEntry]:
        """기존 승인 세트에 드래프트 변경분을 덮어씌운 후보 세트를 만든다."""

        merged = {self._logical_key(entry): entry for entry in base_entries}
        for draft in draft_entries:
            merged[self._logical_key(draft)] = draft
        return list(merged.values())

    def _logical_key(self, entry: ManualEntry) -> str:
        """업무구분/에러코드 기반 논리 키 생성 (없으면 topic까지 포함)."""

        business = entry.business_type or "default"
        error = entry.error_code or "none"
        topic_part = (entry.topic or "").strip().lower()
        if entry.business_type is None and entry.error_code is None and topic_part:
            return f"{business}::{error}::{topic_part}"
        return f"{business}::{error}"

    def _to_snapshot(
        self,
        entry: ManualEntry,
        *,
        logical_key: str | None = None,
    ) -> ManualDiffEntrySnapshot:
        return ManualDiffEntrySnapshot(
            logical_key=logical_key or self._logical_key(entry),
            keywords=list(entry.keywords or []),
            topic=entry.topic,
            background=entry.background,
            guideline=entry.guideline,
            business_type=entry.business_type,
            error_code=entry.error_code,
        )

    def _diff_fields(self, base: ManualEntry, compare: ManualEntry) -> list[str]:
        """변경된 필드 목록 계산."""

        changed: list[str] = []
        fields = ("keywords", "topic", "background", "guideline")
        for field in fields:
            before = getattr(base, field, None)
            after = getattr(compare, field, None)
            if field == "keywords":
                before = list(before or [])
                after = list(after or [])
            if before != after:
                changed.append(field)
        return changed

    async def _resolve_versions_for_diff(
        self,
        *,
        business_type: str | None,
        error_code: str | None,
        base_version: str | None,
        compare_version: str | None,
    ) -> tuple[ManualVersion | None, ManualVersion | None]:
        """
        Diff 시나리오별 base/compare 버전 결정 (그룹 기반)
        """

        if compare_version and base_version is None:
            raise ValidationError("compare_version을 사용할 때는 base_version을 함께 지정하세요.")

        if base_version and compare_version:
            base = await self.version_repo.get_by_version(
                base_version,
                business_type=business_type,
                error_code=error_code,
            )
            compare = await self.version_repo.get_by_version(
                compare_version,
                business_type=business_type,
                error_code=error_code,
            )
            if base is None:
                raise RecordNotFoundError(
                    f"Base version '{base_version}' not found in group {business_type}::{error_code}"
                )
            if compare is None:
                raise RecordNotFoundError(
                    f"Compare version '{compare_version}' not found in group {business_type}::{error_code}"
                )
            return base, compare

        if base_version and compare_version is None:
            base = await self.version_repo.get_by_version(
                base_version,
                business_type=business_type,
                error_code=error_code,
            )
            if base is None:
                raise RecordNotFoundError(
                    f"Base version '{base_version}' not found in group {business_type}::{error_code}"
                )
            latest = await self.version_repo.get_latest_version(
                business_type=business_type,
                error_code=error_code,
            )
            if latest is None:
                raise RecordNotFoundError("비교할 최신 버전이 없습니다.")
            if latest.id == base.id:
                versions = await self.version_repo.list_versions(
                    business_type=business_type,
                    error_code=error_code,
                    limit=2,
                )
                if len(versions) < 2:
                    raise ValidationError("동일 버전을 비교할 수 없습니다. 다른 버전을 지정하세요.")
                return versions[1], versions[0]
            return base, latest

        versions = await self.version_repo.list_versions(
            business_type=business_type,
            error_code=error_code,
            limit=2,
        )
        if len(versions) < 2:
            raise ValidationError("최신/직전 비교를 위해 최소 2개 버전이 필요합니다.")
        return versions[1], versions[0]

    def _next_version_number(self, latest: ManualVersion | None) -> int:
        if latest is None:
            return 1
        try:
            return int(latest.version) + 1
        except ValueError:
            logger.warning("version_parse_failed", latest_version=latest.version)
            return 1

    async def _index_manual_vector(self, manual: ManualEntry) -> None:
        """APPROVED 메뉴얼을 VectorStore에 인덱싱 (재사용 가능 헬퍼)."""

        if self.vectorstore is None:
            logger.warning("manual_vectorstore_not_configured_skip_index", manual_id=str(manual.id))
            return

        text = self._build_manual_text(manual)
        metadata = {
            "business_type": manual.business_type,
            "error_code": manual.error_code,
            "created_at": manual.created_at,
        }

        try:
            await self.vectorstore.index_document(
                id=manual.id,
                text=text,
                metadata=metadata,
            )
            logger.info("manual_indexed", manual_id=str(manual.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("manual_index_failed", manual_id=str(manual.id), error=str(exc))
            metrics_counter("vector_index_failure", target="manual")

    def _build_manual_text(self, manual: ManualEntry) -> str:
        parts = [
            "[키워드] " + ", ".join(manual.keywords or []),
            f"[주제] {manual.topic}",
            f"[배경] {manual.background}",
            f"[가이드라인] {manual.guideline}",
        ]
        return "\n".join(parts)

    def _summarize_manual(self, manual: ManualEntry | None) -> str | None:
        if manual is None:
            return None
        return f"{manual.topic} | {manual.background[:80]}" if manual.background else manual.topic

    def _resolve_business_type(self, manual: ManualEntry | None) -> BusinessType | None:
        if manual is None or manual.business_type is None:
            return None
        try:
            return BusinessType(manual.business_type)
        except ValueError:
            logger.warning(
                "unknown_business_type",
                manual_id=str(manual.id),
                business_type=manual.business_type,
            )
            return None

    @measure_latency("manual_search")
    async def search_manuals(self, params: ManualSearchParams) -> list[ManualSearchResult]:
        if self.vectorstore is None:
            logger.warning("manual_vectorstore_not_configured_skip_search")
            return []

        metadata_filter = {
            k: v
            for k, v in {
                "business_type": params.business_type,
                "error_code": params.error_code,
            }.items()
            if v is not None
        }

        vector_results = await self.vectorstore.search(
            query=params.query,
            top_k=params.top_k,
            metadata_filter=metadata_filter or None,
        )

        # Apply similarity threshold filter
        threshold = settings.search_similarity_threshold
        filtered_results = [res for res in vector_results if res.score >= threshold]

        if not filtered_results:
            logger.info(
                "manual_search_no_results_above_threshold",
                query=params.query,
                threshold=threshold,
                total_results=len(vector_results),
            )
            return []

        manuals = await self.manual_repo.find_by_ids([res.id for res in filtered_results])
        manual_map = {m.id: m for m in manuals}

        base_results: list[dict[str, Any]] = []
        for res in filtered_results:
            manual = manual_map.get(res.id)
            if manual is None:
                continue
            if params.status and manual.status != params.status:
                continue
            meta = {
                "business_type": (
                    res.metadata.get("business_type") if res.metadata else manual.business_type
                ),
                "error_code": res.metadata.get("error_code") if res.metadata else manual.error_code,
                "created_at": res.metadata.get("created_at") if res.metadata else manual.created_at,
            }
            base_results.append({"item": manual, "score": res.score, "metadata": meta})

        reranked = rerank_results(
            base_results,
            domain_weight_config={
                "business_type": params.business_type,
                "error_code": params.error_code,
                "business_type_weight": 0.05,
                "error_code_weight": 0.05,
            },
            recency_weight_config={"weight": 0.05, "half_life_days": 30},
        )

        # business_type 공통코드 매핑 조회 (한 번만)
        business_type_items = await self.common_code_item_repo.get_by_group_code(
            "BUSINESS_TYPE", is_active_only=True
        )
        business_type_map = {
            item.code_key: item.code_value for item in business_type_items
        }

        results = []
        for item in reranked:
            manual = item["item"]
            manual_response = ManualEntryResponse.model_validate(manual)
            
            # business_type_name 추가
            manual_response = manual_response.model_copy(
                update={
                    "business_type_name": business_type_map.get(manual.business_type)
                }
            )

            results.append(
                ManualSearchResult(
                    manual=manual_response,
                    similarity_score=item.get("reranked_score", item.get("score", 0.0)),
                )
            )

        return results

    async def update_manual(
        self,
        manual_id: UUID,
        payload: ManualEntryUpdate,
    ) -> ManualEntryResponse:
        """DRAFT 상태 메뉴얼 항목 업데이트.

        검증 사항:
        1. manual_id 존재 확인
        2. 상태가 DRAFT인지 확인 (DRAFT 상태에서만 수정 가능)
        3. 필드 유효성 검사
        4. 메뉴얼 업데이트
        5. VectorStore 재인덱싱 (상태가 APPROVED로 변경된 경우)
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        if manual.status != ManualStatus.DRAFT:
            raise ValidationError(
                f"DRAFT 상태인 메뉴얼만 수정 가능합니다. " f"현재 상태: {manual.status.value}"
            )

        # 필드 업데이트 (제공된 필드만)
        if payload.keywords is not None:
            manual.keywords = payload.keywords
        if payload.topic is not None:
            manual.topic = payload.topic
        if payload.background is not None:
            manual.background = payload.background
        if payload.guideline is not None:
            manual.guideline = payload.guideline

        # status 변경 처리
        if payload.status is not None and payload.status != manual.status:
            if payload.status == ManualStatus.APPROVED:
                # APPROVED로 변경될 때는 버전 관리 로직 필요
                # 하지만 PUT은 간단한 update만 지원
                # APPROVED는 별도의 approve 엔드포인트(/approve)를 사용하도록 강제
                raise ValidationError(
                    "APPROVED 상태로 변경하려면 /approve 엔드포인트를 사용하세요."
                )
            manual.status = payload.status

        # 메뉴얼 저장
        await self.manual_repo.update(manual)

        logger.info(
            "manual_updated",
            manual_id=str(manual_id),
            new_status=manual.status.value,
        )

        response = ManualEntryResponse.model_validate(manual)
        
        # business_type_name 조회 및 추가
        if manual.business_type:
            business_type_items = await self.common_code_item_repo.get_by_group_code(
                "BUSINESS_TYPE", is_active_only=True
            )
            business_type_map = {
                item.code_key: item.code_value for item in business_type_items
            }
            response = response.model_copy(
                update={
                    "business_type_name": business_type_map.get(manual.business_type)
                }
            )
        
        return response

    async def _create_review_task(
        self,
        *,
        consultation: Consultation,
        new_entry: ManualEntry,
        old_entry: ManualEntry | None = None,
        comparison_type: ComparisonType = ComparisonType.NEW,
        similarity_score: float | None = None,
        compare_version: str | None = None,
        reason: str = "auto_detected",
        auto_merged: bool = False,
    ) -> ManualReviewTask:
        """
        리뷰 태스크 생성 (v2.1 확장)

        Args:
            consultation: 원본 상담
            new_entry: 신규 메뉴얼 초안
            old_entry: 기존 메뉴얼 (있으면)
            comparison_type: SIMILAR/SUPPLEMENT/NEW
            similarity_score: 유사도 점수
            reason: 태스크 생성 사유
            auto_merged: SUPPLEMENT 경로에서 자동 병합했는지 여부
        """
        reviewer_dept_id = await self._resolve_reviewer_department_id(consultation)

        task = ManualReviewTask(
            old_entry_id=old_entry.id if old_entry else None,
            new_entry_id=new_entry.id,
            similarity=similarity_score,
            comparison_type=comparison_type,
            compare_version=compare_version,
            status=TaskStatus.TODO,
            decision_reason=reason,
            reviewer_department_id=reviewer_dept_id,
        )

        if auto_merged and comparison_type == ComparisonType.SUPPLEMENT:
            # SUPPLEMENT 경로: LLM으로 자동 병합
            diff_json, diff_text = await self._call_llm_compare(old_entry, new_entry)
            task.review_notes = (
                f"Auto-merged via LLM. Old: {old_entry.id}, New: {new_entry.id}"
            )

        await self.review_repo.create(task)
        return task

    async def _resolve_reviewer_department_id(
        self,
        consultation: Consultation,
    ) -> UUID | None:
        """
        상담자의 소속 부서를 기반으로 검토 태스크 노출 대상을 결정한다.
        """
        if not consultation.employee_id:
            return None

        user = (
            await self.user_repo.get_with_departments_by_employee_id(
                consultation.employee_id
            )
        )
        if user is None:
            return None

        primary_link = next(
            (link for link in user.department_links if link.is_primary), None
        )
        if primary_link:
            return primary_link.department_id

        if user.department_links:
            return user.department_links[0].department_id

        return None

    async def _apply_replacement(
        self,
        *,
        new_manual: ManualEntry,
        old_manual_id: UUID,
        comparison_type: ComparisonType,
        similarity_score: float | None,
        approver_id: UUID,
    ) -> None:
        """
        기존 메뉴얼을 deprecate하고 대체 관계를 기록.
        """
        old_manual = await self.manual_repo.get_by_id(old_manual_id)
        if old_manual is None:
            logger.warning(
                "manual_replacement_old_manual_missed",
                old_manual_id=str(old_manual_id),
            )
            return

        old_manual.status = ManualStatus.DEPRECATED
        old_manual.replaced_by_manual_id = new_manual.id
        new_manual.replaced_manual_id = old_manual.id
        await self.manual_repo.update(old_manual)

        await self._log_replacement_event(
            old_manual_id=old_manual.id,
            new_manual_id=new_manual.id,
            comparison_type=comparison_type,
            similarity_score=similarity_score,
            approver_id=approver_id,
        )

    async def _log_replacement_event(
        self,
        *,
        old_manual_id: UUID,
        new_manual_id: UUID,
        comparison_type: ComparisonType,
        similarity_score: float | None,
        approver_id: UUID,
    ) -> None:
        event = {
            "event_type": "manual_replaced",
            "old_manual_id": str(old_manual_id),
            "new_manual_id": str(new_manual_id),
            "comparison_type": comparison_type.value,
            "similarity_score": similarity_score,
            "approver_id": str(approver_id),
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger.info("manual_replacement_event", **event)

    async def _enrich_manual_entry_response(
        self,
        entry: ManualEntry,
        business_type_map: dict[str, str] | None = None,
    ) -> ManualEntryResponse:
        """
        ManualEntry를 ManualEntryResponse로 변환하고 business_type_name 추가

        Args:
            entry: ManualEntry 객체
            business_type_map: 공통코드 매핑 (선택사항, None이면 조회)

        Returns:
            business_type_name이 포함된 ManualEntryResponse
        """
        response = ManualEntryResponse.model_validate(entry)

        if entry.business_type:
            if not business_type_map:
                business_type_items = await self.common_code_item_repo.get_by_group_code(
                    "BUSINESS_TYPE", is_active_only=True
                )
                business_type_map = {
                    item.code_key: item.code_value for item in business_type_items
                }

            response = response.model_copy(
                update={
                    "business_type_name": business_type_map.get(entry.business_type)
                }
            )

        return response

    async def _get_business_type_name(self, manual: ManualEntry | None) -> str | None:
        """
        공통코드에서 business_type의 이름(code_value)을 조회

        Args:
            manual: ManualEntry 또는 None

        Returns:
            업무구분 이름 (예: "인터넷뱅킹") 또는 None
        """
        if manual is None or manual.business_type is None:
            return None

        try:
            # BUSINESS_TYPE 그룹의 항목들 조회
            items = await self.common_code_item_repo.get_by_group_code(
                "BUSINESS_TYPE", is_active_only=True
            )

            # business_type 코드와 일치하는 항목 찾기
            for item in items:
                if item.code_key == manual.business_type:
                    return item.code_value

            # 일치하는 항목이 없으면 None 반환
            logger.warning(
                "business_type_not_found_in_common_code",
                manual_id=str(manual.id),
                business_type=manual.business_type,
            )
            return None
        except Exception as e:
            logger.warning(
                "error_getting_business_type_name",
                manual_id=str(manual.id),
                business_type=manual.business_type,
                error=str(e),
            )
            return None

    async def delete_manual(
        self,
        manual_id: UUID,
    ) -> None:
        """
        DRAFT 상태 메뉴얼 항목 삭제.

        검증 사항:
        1. manual_id 존재 확인
        2. 상태가 DRAFT인지 확인 (DRAFT 상태에서만 삭제 가능)
        3. 벡터스토어에서 삭제
        4. 관련 리뷰 태스크 삭제

        Raises:
            RecordNotFoundError: 메뉴얼을 찾을 수 없음
            ValidationError: DRAFT 상태가 아님
        """
        # 1. 메뉴얼 존재 확인
        manual = await self.manual_repo.get_by_id_or_raise(manual_id)

        # 2. DRAFT 상태 확인
        if manual.status != ManualStatus.DRAFT:
            raise ValidationError(
                f"DRAFT 상태인 메뉴얼만 삭제 가능합니다. 현재 상태: {manual.status}"
            )

        # 3. 벡터스토어에서 삭제 (실패해도 계속 진행)
        if self.vectorstore:
            try:
                await self.vectorstore.delete(str(manual_id), "manual")
            except Exception as e:
                logger.warning(
                    "failed_to_delete_from_vectorstore",
                    manual_id=str(manual_id),
                    error=str(e),
                )

        # 4. 관련 리뷰 태스크 삭제
        review_tasks = await self.review_repo.find_by_manual_id(manual_id)
        for task in review_tasks:
            await self.review_repo.delete(task)

        # 5. 메뉴얼 삭제
        await self.manual_repo.delete(manual)
        await self.session.commit()

        logger.info(
            "manual_deleted",
            manual_id=str(manual_id),
            business_type=manual.business_type,
            error_code=manual.error_code,
        )


    async def get_review_tasks_by_manual_id(
        self,
        manual_id: UUID,
        current_user: User,
    ) -> list[ManualReviewTaskResponse]:
        """
        Get review tasks for a specific manual (by new_entry_id)

        Used by frontend to display review logic information for a manual

        Args:
            manual_id: Manual entry UUID (matches new_entry_id)

        Returns:
            List of review task responses enriched with manual info
        """
        review_repo = ManualReviewTaskRepository(self.session)
        reviewer_department_ids: list[UUID] | None = None
        if current_user.role != UserRole.ADMIN:
            department_ids = get_user_department_ids(current_user)
            reviewer_department_ids = department_ids or None

        tasks = await review_repo.find_by_manual_id(
            manual_id,
            reviewer_department_ids=reviewer_department_ids,
        )

        visible_tasks = (
            tasks if current_user.role == UserRole.ADMIN else filter_tasks_for_user(current_user, tasks)
        )
        if tasks and not visible_tasks:
            raise AuthorizationError("해당 메뉴얼 검토 태스크를 조회할 권한이 없습니다.")

        # Get the manual entry model to retrieve related info
        manual_model = await self.manual_repo.get_by_id(manual_id)
        if manual_model is None:
            return []

        # Get business type name for new entry
        business_type_items = await self.common_code_item_repo.get_by_group_code(
            "BUSINESS_TYPE", is_active_only=True
        )
        business_type_map = {
            item.code_key: item.code_value for item in business_type_items
        }

        result = []
        for task in visible_tasks:
            # Get old manual info if exists
            old_manual_summary = None
            old_business_type = None
            old_business_type_name = None
            old_error_code = None
            old_manual_topic = None

            if task.old_entry_id:
                old_manual = await self.manual_repo.get_by_id(task.old_entry_id)
                if old_manual:
                    old_manual_summary = old_manual.background
                    old_business_type = old_manual.business_type
                    old_business_type_name = business_type_map.get(old_business_type)
                    old_error_code = old_manual.error_code
                    old_manual_topic = old_manual.topic

            # Build response
            response = ManualReviewTaskResponse(
                id=task.id,
                old_entry_id=task.old_entry_id,
                new_entry_id=task.new_entry_id,
                similarity=task.similarity,
                status=task.status,
                reviewer_id=task.reviewer_id,
                reviewer_department_id=task.reviewer_department_id,
                review_notes=task.review_notes,
                old_manual_summary=old_manual_summary,
                new_manual_summary=manual_model.background,
                business_type=manual_model.business_type,
                business_type_name=business_type_map.get(manual_model.business_type),
                new_error_code=manual_model.error_code,
                new_manual_topic=manual_model.topic,
                new_manual_keywords=manual_model.keywords,
                old_business_type=old_business_type,
                old_business_type_name=old_business_type_name,
                old_error_code=old_error_code,
                old_manual_topic=old_manual_topic,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            result.append(response)

        return result
