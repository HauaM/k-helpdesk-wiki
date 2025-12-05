"""
Manual Service (FR-2/FR-9 1차 구현)

상담을 기반으로 메뉴얼 초안을 생성하고, 환각 검증에 실패하면 리뷰 태스크를 생성한다.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
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
)
from app.vectorstore.protocol import VectorStoreProtocol
from app.services.rerank import rerank_results
from app.services.validation import (
    validate_keywords_in_source,
    validate_sentences_subset_of_source,
)

logger = get_logger(__name__)


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
            raise RecordNotFoundError(
                f"Consultation(id={request.consultation_id}) not found"
            )

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
            logger.warning("manual_vectorstore_not_configured_skip_conflict", manual_id=str(manual.id))
            return None

        query_text = self._build_manual_text(manual)
        vector_results = await self.vectorstore.search(
            query=query_text,
            top_k=top_k,
        )

        candidate_ids = [res.id for res in vector_results if res.score >= similarity_threshold and res.id != manual.id]
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
    ) -> tuple[dict | None, str | None]:
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

        base_results: list[dict] = []
        for res in vector_results:
            manual = manual_map.get(res.id)
            if manual is None:
                continue
            if params.status and manual.status != params.status:
                continue
            meta = {
                "business_type": res.metadata.get("business_type") if res.metadata else manual.business_type,
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
