"""
Service Layer Base Classes

Repository/VectorStore/LLM/Queue 인터페이스를 조합해 공통 패턴을 정의한다.
FR-1/FR-6/FR-11: 상담 저장·검색 및 메타데이터 기반 검색 정확도 요구사항을 지원하는
서비스 계층의 표준 베이스를 제공한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from app.core.exceptions import KHWException
from app.core.logging import get_logger
from app.llm.protocol import LLMClientProtocol
from app.queue.protocol import QueueProtocol
from app.schemas.base import BaseSchema
from app.schemas.consultation import (
    ConsultationCreate,
    ConsultationResponse,
    ConsultationSearchParams,
    ConsultationSearchResponse,
)
from app.vectorstore.protocol import VectorStoreProtocol


T = TypeVar("T")


class RepositoryProtocol(Protocol):
    """
    최소 CRUD 인터페이스

    FR-1: 상담/메뉴얼 등 도메인 레코드 저장을 위한 추상 레포지토리 계약을 정의한다.
    """

    async def create(self, obj: Any) -> Any:
        """레코드 생성."""

    async def get_by_id(self, id: Any) -> Any:
        """PK 기반 단건 조회."""

    async def delete(self, obj: Any) -> None:
        """레코드 삭제."""


class BaseService(ABC):
    """
    공통 로깅·에러 헬퍼를 제공하는 서비스 베이스 클래스.

    FR-1/FR-6/FR-11: 서비스 메서드가 RDB 기록, Vector 검색, 메타데이터 필터링을
    일관되게 로깅·에러 변환할 수 있도록 MCP Ready 규칙에 맞춘 베이스를 제공한다.
    """

    def __init__(
        self,
        *,
        repository: RepositoryProtocol,
        vectorstore: VectorStoreProtocol | None = None,
        llm_client: LLMClientProtocol | None = None,
        queue: QueueProtocol | None = None,
    ) -> None:
        self.repository = repository
        self.vectorstore = vectorstore
        self.llm_client = llm_client
        self.queue = queue
        self.logger = get_logger(self.__class__.__name__)

    def _log_start(self, operation: str, payload: BaseSchema | None = None) -> None:
        """
        서비스 메서드 진입 시 공통 로그를 남긴다.

        FR-6/FR-11: 검색·필터 파라미터를 구조화해 기록함으로써 추후 정확도 튜닝 시
        근거 데이터를 확보한다.
        """

        serialized = payload.model_dump(exclude_none=True) if payload else None
        self.logger.info("service_operation_start", operation=operation, payload=serialized)

    def _log_success(self, operation: str, metadata: dict[str, Any] | None = None) -> None:
        """
        성공 시 표준 로그를 남긴다.

        FR-1/FR-6: DB 작성·검색 성공 이벤트를 일관된 키로 기록해 감사 추적을 단순화한다.
        """

        meta = metadata or {}
        self.logger.info("service_operation_success", operation=operation, **meta)

    def _log_failure(self, operation: str, error: Exception) -> None:
        """
        실패 이벤트를 구조화하여 로깅한다.

        FR-11: VectorStore/Queue 오류를 포함한 메타데이터 파이프라인 실패를 추적한다.
        """

        self.logger.error(
            "service_operation_failed",
            operation=operation,
            error=str(error),
        )

    async def _execute_with_handling(
        self,
        operation: str,
        action: Callable[[], Awaitable[T]],
        *,
        error_mapper: Callable[[Exception], KHWException] | None = None,
    ) -> T:
        """
        공통 실행 래퍼: 시작/성공/실패 로그와 예외 변환을 담당한다.

        FR-1/FR-6: DB·VectorStore·Queue 작업의 예외를 KHWException으로 변환해
        API 계층과 MCP 에이전트가 동일한 에러 규약을 사용할 수 있게 한다.
        """

        self._log_start(operation)
        try:
            result = await action()
        except KHWException as exc:  # 이미 표준화된 에러는 그대로 전달
            self._log_failure(operation, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - 서비스 경계에서 변환 처리
            self._log_failure(operation, exc)
            if error_mapper:
                mapped_error = error_mapper(exc)
                raise mapped_error from exc
            raise

        self._log_success(operation)
        return result


class ConsultationServiceInterface(BaseService, ABC):
    """
    상담 도메인 서비스 인터페이스 시그니처.

    FR-1/FR-6/FR-11: 상담 저장, 의미 기반 검색, 메타데이터 필터링을 담당하며
    FastAPI Request/Response를 알지 않는 MCP Ready 규칙을 따른다.
    모든 public 메서드는 Pydantic 스키마를 입력/출력으로 사용한다.
    """

    @abstractmethod
    async def create_consultation(self, payload: ConsultationCreate) -> ConsultationResponse:
        """
        상담을 생성하고 Vector 인덱싱을 예약한다.

        FR-1/FR-11: RDB 저장 후 branch/business/error 메타데이터를 포함한 벡터 인덱싱
        (직접 또는 Queue 활용)까지 포함하는 오케스트레이션을 수행한다.
        """

    @abstractmethod
    async def search_consultations(
        self,
        params: ConsultationSearchParams,
    ) -> ConsultationSearchResponse:
        """
        의미 기반 상담 검색을 수행한다.

        FR-6/FR-11: VectorStore Top-K 검색 후 메타 필터(branch_code/business_type/error_code)
        를 적용한 재정렬/Threshold 검사를 책임진다.
        """
