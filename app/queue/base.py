"""
Retry Queue 인터페이스 정의

VectorStore 인덱싱 재시도를 위해 FR-11에서 요구하는 지수 백오프,
재시도 횟수, Dead Letter 표현을 지원한다.
"""

from typing import Protocol, runtime_checkable

from app.queue.schemas import RetryStatus, VectorIndexJob


@runtime_checkable
class RetryQueue(Protocol):
    """Retry Queue 추상 인터페이스."""

    def enqueue(self, job: VectorIndexJob) -> VectorIndexJob:
        """작업을 큐에 추가하고 job_id를 부여한다."""

    def mark_failed(self, job_id: str, error: str) -> VectorIndexJob:
        """실패 기록 및 백오프 스케줄링/Dead Letter 전환."""

    def mark_success(self, job_id: str) -> VectorIndexJob:
        """작업 성공 처리."""


class RetryQueueStub(RetryQueue):
    """실제 구현 없이 서비스 계층 타입 체크용 Stub."""

    def enqueue(self, job: VectorIndexJob) -> VectorIndexJob:  # pragma: no cover - stub
        raise NotImplementedError("RetryQueue.enqueue 구현체가 필요합니다")

    def mark_failed(self, job_id: str, error: str) -> VectorIndexJob:  # pragma: no cover - stub
        raise NotImplementedError("RetryQueue.mark_failed 구현체가 필요합니다")

    def mark_success(self, job_id: str) -> VectorIndexJob:  # pragma: no cover - stub
        raise NotImplementedError("RetryQueue.mark_success 구현체가 필요합니다")
