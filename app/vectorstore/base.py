"""
VectorStore interface 정의

RPF FR-11에 명시된 메타데이터(branch_code/business_type/error_code/created_at)
스키마를 기반으로 VectorStore 구현체가 교체 가능하도록 추상화를 제공한다.
"""

from typing import Protocol, Sequence, runtime_checkable

from app.vectorstore.schemas import SearchResult, VectorItem


@runtime_checkable
class VectorStore(Protocol):
    """VectorStore 추상 인터페이스."""

    def add(self, vectors: list[VectorItem]) -> None:
        """
        벡터 데이터 일괄 추가.

        Args:
            vectors: 인덱싱할 벡터 아이템 리스트.
        """

    def search(
        self,
        query_embedding: Sequence[float],
        top_k: int,
        metadata_filter: dict | None = None,
    ) -> list[SearchResult]:
        """
        임베딩 기반 유사도 검색.

        Args:
            query_embedding: 쿼리 임베딩 벡터.
            top_k: 반환할 최대 결과 수.
            metadata_filter: FR-11 메타데이터 필터(branch_code/business_type/error_code/created_at 등).
        """


class VectorStoreStub(VectorStore):
    """실제 구현 없이 서비스 계층 타입 체킹을 위한 Stub."""

    def add(self, vectors: list[VectorItem]) -> None:  # pragma: no cover - stub
        raise NotImplementedError("VectorStore.add 구현체가 필요합니다")

    def search(
        self,
        query_embedding: Sequence[float],
        top_k: int,
        metadata_filter: dict | None = None,
    ) -> list[SearchResult]:  # pragma: no cover - stub
        raise NotImplementedError("VectorStore.search 구현체가 필요합니다")
