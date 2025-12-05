"""
Retry Queue DTO 정의

FR-11: 지수 백오프, 재시도 횟수, Dead Letter 표현을 위한 필드 포함.
"""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from app.schemas.base import BaseSchema
from app.vectorstore.schemas import VectorItem


class RetryStatus(str, Enum):
    PENDING = "PENDING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    DEAD_LETTER = "DEAD_LETTER"


class VectorIndexJob(BaseSchema):
    """VectorStore 인덱싱 작업 재시도 큐용 DTO."""

    job_id: str | None = Field(default=None, description="큐 내부 작업 ID")
    target_type: Literal["CONSULTATION", "MANUAL"]
    vector: VectorItem
    max_retries: int = Field(default=5, ge=1)
    attempts: int = Field(default=0, ge=0)
    backoff_factor: float = Field(default=2.0, ge=1.0)
    base_delay_seconds: float = Field(default=1.0, ge=0.1)
    next_retry_at: datetime | None = None
    last_error: str | None = None
    status: RetryStatus = RetryStatus.PENDING
    dead_letter_reason: str | None = None
