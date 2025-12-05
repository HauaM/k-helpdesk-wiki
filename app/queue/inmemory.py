"""
RetryQueue InMemory 구현체

Redis/PostgreSQL 구현 이전에 사용할 수 있는 간단한 메모리 기반 큐.
지수 백오프와 Dead Letter 전환 로직을 제공한다.
"""

from datetime import datetime, timedelta
from uuid import uuid4

from app.queue.base import RetryQueue
from app.queue.schemas import RetryStatus, VectorIndexJob


class InMemoryRetryQueue(RetryQueue):
    """개발/테스트용 InMemory Retry Queue."""

    def __init__(self) -> None:
        self._jobs: dict[str, VectorIndexJob] = {}

    def enqueue(self, job: VectorIndexJob) -> VectorIndexJob:
        job_id = job.job_id or str(uuid4())
        prepared = job.model_copy(
            update={
                "job_id": job_id,
                "attempts": 0,
                "status": RetryStatus.PENDING,
                "dead_letter_reason": None,
                "last_error": None,
                "next_retry_at": None,
            }
        )
        self._jobs[job_id] = prepared
        return prepared

    def mark_failed(self, job_id: str, error: str) -> VectorIndexJob:
        job = self._get(job_id)
        attempts = job.attempts + 1

        delay_seconds = job.base_delay_seconds * (job.backoff_factor ** max(attempts - 1, 0))
        next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)

        if attempts >= job.max_retries:
            status = RetryStatus.DEAD_LETTER
            next_retry_at = None
            dead_letter_reason = error
        else:
            status = RetryStatus.RETRYING
            dead_letter_reason = None

        updated = job.model_copy(
            update={
                "attempts": attempts,
                "status": status,
                "last_error": error,
                "next_retry_at": next_retry_at,
                "dead_letter_reason": dead_letter_reason,
            }
        )
        self._jobs[job_id] = updated
        return updated

    def mark_success(self, job_id: str) -> VectorIndexJob:
        job = self._get(job_id)
        updated = job.model_copy(
            update={
                "status": RetryStatus.COMPLETED,
                "next_retry_at": None,
                "dead_letter_reason": None,
                "last_error": None,
            }
        )
        self._jobs[job_id] = updated
        return updated

    def _get(self, job_id: str) -> VectorIndexJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"job_id={job_id} not found") from exc
