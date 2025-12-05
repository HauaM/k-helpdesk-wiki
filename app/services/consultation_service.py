"""
Consultation Service (FR-1 기준 구현)

상담 등록 시 RDB 저장 후 VectorStore 인덱싱을 시도하고,
인덱싱 실패 시 재시도 큐에 작업을 남긴다. FastAPI 의존성이 없는
순수 서비스 클래스다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VectorIndexError
from app.core.logging import get_logger, measure_latency, metrics_counter
from app.models.consultation import Consultation
from app.queue.base import RetryQueue
from app.queue.schemas import VectorIndexJob
from app.repositories.consultation_repository import (
    ConsultationRepository,
    ConsultationSearchFilters as RepoSearchFilters,
)
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationSearchFilters,
    ConsultationSearchRequest,
    ConsultationSearchResult,
    ConsultationSearchVectorMetadata,
)
from app.services.rerank import rerank_results
from app.vectorstore.protocol import VectorStoreProtocol
from app.vectorstore.schemas import VectorItem, VectorMetadata

logger = get_logger(__name__)


class ConsultationService:
    """상담 도메인 서비스. FastAPI 레이어와 분리된 순수 비즈니스 로직."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        vectorstore: VectorStoreProtocol | None,
        retry_queue: RetryQueue | None,
        repository: ConsultationRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or ConsultationRepository(session)
        self.vectorstore = vectorstore
        self.retry_queue = retry_queue

    async def create_consultation(self, data: ConsultationCreate) -> ConsultationResponse:
        """FR-1: 상담 등록.

        1) RDB 저장 → 2) VectorStore 인덱싱 시도 → 3) 실패 시 재시도 큐 등록.
        """

        logger.info(
            "consultation_create_request",
            branch_code=data.branch_code,
            employee_id=data.employee_id,
        )

        consultation = await self.repository.create_consultation(data)

        try:
            await self._index_consultation_vector(consultation)
        except Exception as exc:  # noqa: BLE001 - 실패 시 큐 등록 후 전달하지 않음
            self._enqueue_index_retry(consultation, error=str(exc))

        return ConsultationResponse.model_validate(consultation)

    async def _index_consultation_vector(self, consultation: Consultation) -> None:
        """VectorStore 인덱싱 헬퍼.

        실제 Embedding 생성기는 추후 교체(TODO). 현재는 summary/inquiry/action을
        단순 결합한 텍스트를 VectorStore에 전달한다.
        """

        if self.vectorstore is None:
            logger.warning("vectorstore_not_configured_skip_index", consultation_id=str(consultation.id))
            return

        text_for_embedding = self._build_embedding_text(consultation)
        metadata = self._build_vector_metadata(consultation)

        try:
            await self.vectorstore.index_document(
                id=consultation.id,
                text=text_for_embedding,
                metadata=metadata,
            )
            logger.info("consultation_indexed", consultation_id=str(consultation.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("consultation_index_failed", consultation_id=str(consultation.id), error=str(exc))
            metrics_counter("vector_index_failure", target="consultation")
            raise VectorIndexError(f"Vector index failed: {exc}")

    def _enqueue_index_retry(self, consultation: Consultation, *, error: str) -> None:
        """인덱싱 실패 시 재시도 큐에 작업을 남긴다."""

        if self.retry_queue is None:
            logger.error(
                "retry_queue_not_configured",
                consultation_id=str(consultation.id),
                error=error,
            )
            return

        vector_metadata = VectorMetadata(**self._build_vector_metadata(consultation))
        job = VectorIndexJob(
            target_type="CONSULTATION",
            vector=VectorItem(
                id=consultation.id,
                embedding=self._build_embedding_stub(),
                metadata=vector_metadata,
            ),
        )

        enqueued = self.retry_queue.enqueue(job)
        logger.info(
            "vector_index_retry_enqueued",
            job_id=enqueued.job_id,
            consultation_id=str(consultation.id),
            error=error,
        )

    def _build_embedding_text(self, consultation: Consultation) -> str:
        """TODO: 실제 Embedding 입력을 구성하는 헬퍼."""

        # 추후 Embedding 서비스 호출 시 이 텍스트를 입력으로 사용한다.
        parts = [
            f"[요약]{consultation.summary}",
            f"[문의]{consultation.inquiry_text}",
            f"[조치]{consultation.action_taken}",
        ]
        return "\n".join(parts)

    def _build_embedding_stub(self) -> list[float]:
        """임시 Embedding 스텁. 실제 Embedding 생성기로 교체 예정."""

        return []

    def _build_vector_metadata(self, consultation: Consultation) -> dict[str, Any]:
        """VectorStore/RetryQueue에 전달할 메타데이터 dict."""

        return {
            "branch_code": consultation.branch_code,
            "business_type": consultation.business_type,
            "error_code": consultation.error_code,
            "created_at": consultation.created_at,
        }

    async def search_consultations(
        self, search_request: ConsultationSearchRequest
    ) -> list[ConsultationSearchResult]:
        """FR-3/FR-8: Vector 검색 + 메타 필터 적용 후 Re-ranking 골격."""

        # latency 측정 (NFR-1)
        search_with_latency = measure_latency("consultation_search")(self._search_consultations)
        return await search_with_latency(search_request)

    async def _search_consultations(
        self, search_request: ConsultationSearchRequest
    ) -> list[ConsultationSearchResult]:
        if self.vectorstore is None:
            logger.warning("vectorstore_not_configured_skip_search")
            return []

        # TODO: query -> embedding 변환 및 LLM/Embedding 호출 (현재는 raw query 사용)
        metadata_filter = self._build_metadata_filter(search_request.filters)

        vector_results = await self.vectorstore.search(
            query=search_request.query,
            top_k=search_request.top_k,
            metadata_filter=metadata_filter or None,
        )

        repo_filters = RepoSearchFilters(
            branch_code=search_request.filters.branch_code,
            business_type=search_request.filters.business_type,
            error_code=search_request.filters.error_code,
        )
        consultations = await self.repository.search_by_ids(
            [res.id for res in vector_results],
            repo_filters,
        )
        consultation_map = {item.id: item for item in consultations}

        base_results: list[dict] = []
        for res in vector_results:
            consultation = consultation_map.get(res.id)
            if consultation is None:
                continue  # 필터에 의해 제외된 케이스

            meta = self._build_search_metadata(res.metadata)
            base_results.append(
                {
                    "item": consultation,
                    "score": res.score,
                    "metadata": meta.model_dump() if meta else {},
                }
            )

        reranked = rerank_results(
            base_results,
            domain_weight_config={
                "business_type": search_request.filters.business_type,
                "error_code": search_request.filters.error_code,
                "business_type_weight": 0.05,
                "error_code_weight": 0.05,
            },
            recency_weight_config={"weight": 0.05, "half_life_days": 30},
        )

        return [
            ConsultationSearchResult(
                consultation=ConsultationResponse.model_validate(item["item"]),
                score=item.get("reranked_score", item.get("score", 0.0)),
                metadata=ConsultationSearchVectorMetadata(**item.get("metadata", {}))
                if item.get("metadata")
                else None,
            )
            for item in reranked
        ]

    def _build_metadata_filter(self, filters: ConsultationSearchFilters) -> dict[str, Any]:
        """VectorStore 검색 시 사용할 메타데이터 필터 dict 구성."""

        metadata = {
            "branch_code": filters.branch_code,
            "business_type": filters.business_type,
            "error_code": filters.error_code,
        }
        return {k: v for k, v in metadata.items() if v is not None}

    def _build_search_metadata(
        self, metadata: dict[str, Any] | None
    ) -> ConsultationSearchVectorMetadata | None:
        if metadata is None:
            return None

        return ConsultationSearchVectorMetadata(
            branch_code=metadata.get("branch_code"),
            business_type=metadata.get("business_type"),
            error_code=metadata.get("error_code"),
            created_at=metadata.get("created_at"),
        )
