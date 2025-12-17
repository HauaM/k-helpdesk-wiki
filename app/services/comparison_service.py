"""
ComparisonService (v2.1 구현)

VectorStore를 사용하여 신규 draft와 기존 메뉴얼을 비교하고,
유사도 점수에 따라 comparison_type을 판정한다.

FR-11(v2.1): Document-Set Version Management with Smart Comparison
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.manual import ManualEntry, ManualStatus
from app.models.task import ComparisonType
from app.repositories.manual_rdb import ManualEntryRDBRepository
from app.services.common_code_service import CommonCodeService
from app.vectorstore.protocol import VectorStoreProtocol

logger = get_logger(__name__)

KEYWORD_COMPRESSION_MIN_OVERLAP = settings.keyword_compression_min_overlap
KEYWORD_COMPRESSION_BONUS_WEIGHT = settings.keyword_compression_bonus_weight
FORBIDDEN_KEYWORD_HINT = "hint_missing_forbidden_keywords"
COMPARISON_VERSION = (
    f"kw{KEYWORD_COMPRESSION_MIN_OVERLAP}_bonus{int(KEYWORD_COMPRESSION_BONUS_WEIGHT * 100)}"
)


@dataclass
class ComparisonResult:
    """비교 결과 데이터 클래스"""

    comparison_type: ComparisonType
    existing_manual: Optional[ManualEntry] = None
    similarity_score: Optional[float] = None
    reason: str = ""
    compare_version: str | None = None


class ComparisonService:
    """신규 draft와 기존 메뉴얼 비교 서비스 (v3.1)"""

    def __init__(
        self,
        *,
        session: AsyncSession,
        vectorstore: VectorStoreProtocol | None = None,
        manual_repo: ManualEntryRDBRepository | None = None,
        common_code_service: CommonCodeService | None = None,
    ) -> None:
        self.session = session
        self.vectorstore = vectorstore
        self.manual_repo = manual_repo or ManualEntryRDBRepository(session)
        self.common_code_service = common_code_service or CommonCodeService(session)
        self._missing_forbidden_keyword_hint = False

    async def compare(
        self,
        new_draft: ManualEntry,
        compare_with_manual_id: UUID | None = None,
        *,
        similarity_threshold_similar: float = 0.95,
        similarity_threshold_supplement: float = 0.7,
    ) -> ComparisonResult:
        """
        신규 draft를 검토 후 best_match를 찾아 comparison_type을 판정한다.
        """

        forbidden_keywords, missing_keyword_hint = await self._load_forbidden_keywords()
        self._missing_forbidden_keyword_hint = missing_keyword_hint

        candidates = await self._collect_candidates(new_draft, compare_with_manual_id)
        if not candidates:
            return ComparisonResult(
                comparison_type=ComparisonType.NEW,
                reason=self._with_keyword_hint("no_candidates"),
                compare_version=COMPARISON_VERSION,
            )

        filtered_candidates, keyword_scores = self._apply_keyword_compression(
            new_draft, candidates, forbidden_keywords
        )

        best_match, best_similarity = await self._select_best_candidate(
            new_draft, filtered_candidates, keyword_scores
        )

        if best_match is None:
            return ComparisonResult(
                comparison_type=ComparisonType.NEW,
                reason=self._with_keyword_hint("no_vector_results"),
                compare_version=COMPARISON_VERSION,
            )

        if best_similarity >= similarity_threshold_similar:
            comparison_type = ComparisonType.SIMILAR
        elif best_similarity >= similarity_threshold_supplement:
            comparison_type = ComparisonType.SUPPLEMENT
        else:
            comparison_type = ComparisonType.NEW

        return ComparisonResult(
            comparison_type=comparison_type,
            existing_manual=best_match if comparison_type != ComparisonType.NEW else None,
            similarity_score=best_similarity,
            reason=self._with_keyword_hint(f"similarity_{best_similarity:.2f}"),
            compare_version=COMPARISON_VERSION,
        )

    async def find_best_match_candidate(
        self,
        new_draft: ManualEntry,
    ) -> ManualEntry | None:
        """
        최초 비교 및 guard용으로 best_match만 재검증할 때 사용.
        """
        forbidden_keywords, missing_keyword_hint = await self._load_forbidden_keywords()
        self._missing_forbidden_keyword_hint = missing_keyword_hint

        candidates = await self._collect_candidates(new_draft, None)
        if not candidates:
            return None

        filtered_candidates, keyword_scores = self._apply_keyword_compression(
            new_draft, candidates, forbidden_keywords
        )

        best_match, _ = await self._select_best_candidate(
            new_draft, filtered_candidates, keyword_scores
        )
        return best_match

    async def _collect_candidates(
        self,
        new_draft: ManualEntry,
        compare_with_manual_id: UUID | None,
    ) -> list[ManualEntry]:
        if compare_with_manual_id:
            manual = await self.manual_repo.get_by_id(compare_with_manual_id)
            if manual and manual.status == ManualStatus.APPROVED:
                return [manual]
            return []

        if not new_draft.business_type or not new_draft.error_code:
            logger.info(
                "comparison_missing_group",
                manual_id=str(new_draft.id),
                business_type=new_draft.business_type,
                error_code=new_draft.error_code,
            )
            return []

        await self.manual_repo.find_latest_by_group(
            business_type=new_draft.business_type,
            error_code=new_draft.error_code,
            status=ManualStatus.APPROVED,
            exclude_id=new_draft.id,
        )

        return await self.manual_repo.find_all_approved_by_group(
            business_type=new_draft.business_type,
            error_code=new_draft.error_code,
        )

    def _apply_keyword_compression(
        self,
        new_draft: ManualEntry,
        candidates: Iterable[ManualEntry],
        forbidden_keywords: frozenset[str],
    ) -> tuple[list[ManualEntry], dict[UUID, int]]:
        keyword_scores: dict[UUID, int] = {}
        filtered_candidates: list[ManualEntry] = list(candidates)
        total_candidates = len(filtered_candidates)

        if not new_draft.keywords:
            return filtered_candidates, keyword_scores

        valid_keywords = self._filter_valid_keywords(new_draft.keywords, forbidden_keywords)
        if not valid_keywords:
            return filtered_candidates, keyword_scores

        overlaps: list[tuple[ManualEntry, int]] = []
        for candidate in filtered_candidates:
            candidate_keywords = self._filter_valid_keywords(candidate.keywords or [], forbidden_keywords)
            overlap = len(set(valid_keywords) & set(candidate_keywords))
            overlaps.append((candidate, overlap))
            keyword_scores[candidate.id] = overlap

        overlap_two_or_more = [candidate for candidate, count in overlaps if count >= KEYWORD_COMPRESSION_MIN_OVERLAP]
        if overlap_two_or_more:
            filtered_candidates = overlap_two_or_more
            logger.info(
                "comparison_candidates_compressed",
                candidate_count=len(filtered_candidates),
                total=total_candidates,
                filter_keywords=valid_keywords,
            )
        else:
            logger.info(
                "comparison_no_compression",
                keywords=valid_keywords,
                message="overlap < min, keeping all candidates (bonus only)",
            )

        return filtered_candidates, keyword_scores

    async def _select_best_candidate(
        self,
        new_draft: ManualEntry,
        candidates: Iterable[ManualEntry],
        keyword_scores: dict[UUID, int],
    ) -> tuple[Optional[ManualEntry], float]:
        if self.vectorstore is None:
            logger.warning("comparison_vectorstore_unavailable", manual_id=str(new_draft.id))
            return None, 0.0

        best_match = None
        best_similarity = 0.0
        best_final_score = 0.0
        new_text = self._build_manual_text(new_draft)

        for candidate in candidates:
            candidate_text = self._build_manual_text(candidate)
            try:
                similarity = await self.vectorstore.similarity(
                    text1=new_text,
                    text2=candidate_text,
                )
            except Exception as exc:
                logger.error(
                    "comparison_similarity_failed",
                    manual_id=str(new_draft.id),
                    candidate_id=str(candidate.id),
                    error=str(exc),
                )
                return None, 0.0
            final_score = similarity
            overlap = keyword_scores.get(candidate.id, 0)
            if overlap == 1:
                final_score += KEYWORD_COMPRESSION_BONUS_WEIGHT

            logger.debug(
                "comparison_similarity",
                manual_id=str(new_draft.id),
                candidate_id=str(candidate.id),
                similarity=f"{similarity:.2f}",
                overlap=overlap,
                final_score=f"{final_score:.2f}",
            )

            if final_score > best_final_score:
                best_final_score = final_score
                best_similarity = similarity
                best_match = candidate

        return best_match, best_similarity

    def _filter_valid_keywords(
        self,
        keywords: Iterable[str],
        forbidden_keywords: frozenset[str],
    ) -> list[str]:
        filtered_keywords: list[str] = []
        for keyword in keywords:
            if not keyword:
                continue
            normalized = keyword.strip()
            if not normalized:
                continue
            if normalized.lower() in forbidden_keywords:
                continue
            filtered_keywords.append(normalized)
        return filtered_keywords

    async def _load_forbidden_keywords(self) -> tuple[frozenset[str], bool]:
        try:
            raw_keywords = await self.common_code_service.get_forbidden_keywords()
        except Exception as exc:
            logger.warning(
                "comparison_forbidden_keywords_fetch_failed",
                error=str(exc),
            )
            return frozenset(), True

        normalized_keywords = frozenset(
            value.strip().lower()
            for value in raw_keywords
            if isinstance(value, str) and value.strip()
        )

        return normalized_keywords, len(normalized_keywords) == 0

    def _with_keyword_hint(self, reason: str) -> str:
        if self._missing_forbidden_keyword_hint:
            if reason:
                return f"{reason};{FORBIDDEN_KEYWORD_HINT}"
            return FORBIDDEN_KEYWORD_HINT
        return reason

    def _build_manual_text(self, manual: ManualEntry) -> str:
        return f"{manual.topic}\n{manual.background}\n{manual.guideline}"
