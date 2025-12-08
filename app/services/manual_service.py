"""
Manual Service (FR-2/FR-9 1차 구현)

상담을 기반으로 메뉴얼 초안을 생성하고, 환각 검증에 실패하면 리뷰 태스크를 생성한다.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID
import time
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    RecordNotFoundError,
    ValidationError,
    BusinessLogicError,
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
from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.models.task import ManualReviewTask, TaskStatus
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.manual_rdb import (
    ManualEntryRDBRepository,
    ManualReviewTaskRepository,
    ManualVersionRepository,
)
from app.schemas.manual import (
    ManualDraftCreateFromConsultationRequest,
    ManualDraftResponse,
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
)
from app.vectorstore.protocol import VectorStoreProtocol
from app.services.rerank import rerank_results
from app.services.validation import (
    validate_keywords_in_source,
    validate_sentences_subset_of_source,
)

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
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.vectorstore = vectorstore
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)
        self.review_repo = review_repo or ManualReviewTaskRepository(session)
        self.version_repo = version_repo or ManualVersionRepository(session)
        self.consultation_repo = consultation_repo or ConsultationRepository(session)

    async def create_draft_from_consultation(
        self, request: ManualDraftCreateFromConsultationRequest
    ) -> ManualDraftResponse:
        """FR-2: 상담 기반 메뉴얼 초안 생성 + FR-9 환각 방지 검증."""

        consultation = await self.consultation_repo.get_by_id(request.consultation_id)
        if consultation is None:
            raise RecordNotFoundError(f"Consultation(id={request.consultation_id}) not found")

        source_text = f"{consultation.inquiry_text}\n{consultation.action_taken}"

        llm_payload = await self._call_llm_for_draft(
            inquiry_text=consultation.inquiry_text,
            action_taken=consultation.action_taken,
            business_type=consultation.business_type,
            error_code=consultation.error_code,
        )

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

        manual_entry = await self._persist_manual_entry(
            consultation_id=consultation.id,
            llm_payload=llm_payload,
            business_type=consultation.business_type,
            error_code=consultation.error_code,
        )

        if has_hallucination:
            await self._create_review_task(
                new_entry=manual_entry,
                reason=";".join(fail_reasons) or "validation_failed",
            )

        return ManualDraftResponse.model_validate(manual_entry)

    async def get_manual(self, manual_id: UUID) -> ManualEntryResponse:
        """메뉴얼 단건 상세 조회."""

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        return ManualEntryResponse.model_validate(manual)

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
        """FR-4/FR-5: 메뉴얼 승인 및 전체 버전 세트 갱신.

        금융권 정책집: 전체 버전 일괄 적용 컨셉을 반영해 모든 승인 시 Version을
        1씩 증가시키며, 동일 키(업무구분/에러코드) 기존 항목은 DEPRECATED 처리한다.
        APPROVED 항목만 VectorStore에 인덱싱한다.
        """

        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        logger.info(
            "manual_approve_start",
            manual_id=str(manual_id),
            approver_id=str(request.approver_id),
        )

        latest_version = await self.version_repo.get_latest_version()
        next_version_num = self._next_version_number(latest_version)
        next_version = ManualVersion(version=str(next_version_num))
        await self.version_repo.create(next_version)

        await self._deprecate_previous_entries(manual)

        manual.status = ManualStatus.APPROVED
        manual.version_id = next_version.id
        await self.manual_repo.update(manual)

        await self._index_manual_vector(manual)

        return ManualVersionInfo(
            version=next_version.version,
            approved_at=next_version.created_at,
        )

    async def list_versions(self, manual_id: UUID) -> list[ManualVersionResponse]:
        """FR-14: 특정 메뉴얼 그룹의 버전 목록 조회 (최신순, 현재 버전 표시 포함).

        같은 business_type/error_code를 가진 메뉴얼들의 버전을 모두 반환합니다.

        Args:
            manual_id: 메뉴얼 ID (그룹을 식별하기 위해 사용)

        Returns:
            버전 목록 (최신순)

        응답 필드:
        - value: 버전 번호 (예: "v2.1")
        - label: 사용자 표시용 레이블 (최신 버전에만 "(현재 버전)" 추가)
        - date: 버전 생성/승인 날짜 (YYYY-MM-DD 형식)
        """

        # 1. 기준 메뉴얼 조회
        manual = await self.manual_repo.get_by_id(manual_id)
        if manual is None:
            raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

        # 2. 같은 그룹의 APPROVED/DEPRECATED 메뉴얼만 조회 (business_type + error_code)
        # DRAFT는 version_id가 NULL이므로 버전 목록에 포함되지 않음
        group_entries = list(
            await self.manual_repo.find_by_business_and_error(
                business_type=manual.business_type,
                error_code=manual.error_code,
                statuses={ManualStatus.APPROVED, ManualStatus.DEPRECATED},
            )
        )

        if not group_entries:
            return []

        # 3. 그룹 메뉴얼들의 버전 ID 추출 (중복 제거)
        version_ids = set()
        for entry in group_entries:
            if entry.version_id is not None:
                version_ids.add(entry.version_id)

        if not version_ids:
            return []

        # 4. 버전 정보 조회 및 정렬 (최신순)
        all_versions = await self.version_repo.list_versions()
        group_versions = [v for v in all_versions if v.id in version_ids]

        if not group_versions:
            return []

        result: list[ManualVersionResponse] = []
        for idx, v in enumerate(group_versions):
            # 가장 최신 버전(첫 번째 항목)에만 "(현재 버전)" 표시
            label = f"{v.version} (현재 버전)" if idx == 0 else v.version

            # created_at을 YYYY-MM-DD 형식으로 변환
            date_str = v.created_at.strftime("%Y-%m-%d")

            result.append(
                ManualVersionResponse(
                    version=v.version,  # alias "version" used here
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
    ) -> list[ManualEntryResponse]:
        """RFP FR-8/General: 메뉴얼 목록 조회"""

        statuses = {status} if status is not None else None
        entries = await self.manual_repo.list_entries(
            statuses=statuses,
            limit=limit,
        )
        return [ManualEntryResponse.model_validate(entry) for entry in entries]

    async def diff_versions(
        self,
        manual_group_id: str,
        *,
        base_version: str | None,
        compare_version: str | None,
        summarize: bool = False,
    ) -> ManualVersionDiffResponse:
        """FR-14 시나리오 A/B: 버전 간 Diff."""

        base, compare = await self._resolve_versions_for_diff(
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
        await self.manual_repo.create(manual_entry)
        return manual_entry

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
        base_version: str | None,
        compare_version: str | None,
    ) -> tuple[ManualVersion | None, ManualVersion | None]:
        """Diff 시나리오별 base/compare 버전 결정."""

        if compare_version and base_version is None:
            raise ValidationError("compare_version을 사용할 때는 base_version을 함께 지정하세요.")

        if base_version and compare_version:
            base = await self.version_repo.get_by_version(base_version)
            compare = await self.version_repo.get_by_version(compare_version)
            if base is None:
                raise RecordNotFoundError(f"Base version {base_version} not found")
            if compare is None:
                raise RecordNotFoundError(f"Compare version {compare_version} not found")
            return base, compare

        if base_version and compare_version is None:
            base = await self.version_repo.get_by_version(base_version)
            if base is None:
                raise RecordNotFoundError(f"Base version {base_version} not found")
            latest = await self.version_repo.get_latest_version()
            if latest is None:
                raise RecordNotFoundError("비교할 최신 버전이 없습니다.")
            if latest.id == base.id:
                versions = await self.version_repo.list_versions(limit=2)
                if len(versions) < 2:
                    raise ValidationError("동일 버전을 비교할 수 없습니다. 다른 버전을 지정하세요.")
                return versions[1], versions[0]
            return base, latest

        versions = await self.version_repo.list_versions(limit=2)
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

    async def _deprecate_previous_entries(self, manual: ManualEntry) -> None:
        """동일 키(업무구분/에러코드)를 가진 기존 승인 메뉴얼을 DEPRECATED 처리."""

        stmt = select(ManualEntry).where(
            ManualEntry.id != manual.id,
            ManualEntry.status == ManualStatus.APPROVED,
            ManualEntry.business_type == manual.business_type,
            ManualEntry.error_code == manual.error_code,
        )
        result = await self.session.execute(stmt)
        to_deprecate = list(result.scalars().all())

        for entry in to_deprecate:
            entry.status = ManualStatus.DEPRECATED
        if to_deprecate:
            await self.session.flush()

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

        manuals = await self.manual_repo.find_by_ids([res.id for res in vector_results])
        manual_map = {m.id: m for m in manuals}

        base_results: list[dict[str, Any]] = []
        for res in vector_results:
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

        return [
            ManualSearchResult(
                manual=ManualEntryResponse.model_validate(item["item"]),
                similarity_score=item.get("reranked_score", item.get("score", 0.0)),
            )
            for item in reranked
        ]

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

        return ManualEntryResponse.model_validate(manual)

    async def _create_review_task(
        self,
        *,
        new_entry: ManualEntry,
        reason: str,
    ) -> ManualReviewTask:
        task = ManualReviewTask(
            old_entry_id=None,
            new_entry_id=new_entry.id,
            similarity=0.0,
            status=TaskStatus.TODO,
            decision_reason=reason,
        )
        await self.review_repo.create(task)
        return task
