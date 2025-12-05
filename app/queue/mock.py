"""
Mock Queue Implementation
In-memory queue for development/testing
"""

from typing import Dict
from uuid import uuid4
import asyncio

from app.queue.protocol import QueueTaskResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class MockQueue:
    """
    Mock queue using in-memory storage

    For development/testing without Celery/Redis
    """

    def __init__(self):
        self._tasks: Dict[str, QueueTaskResult] = {}
        self._dlq: Dict[str, QueueTaskResult] = {}
        logger.info("mock_queue_initialized")

    async def enqueue(
        self,
        task_name: str,
        task_data: dict,
        priority: int = 0,
    ) -> str:
        """
        Add task to in-memory queue
        """
        task_id = str(uuid4())

        # Simulate async operation
        await asyncio.sleep(0.01)

        # Store task
        task_result = QueueTaskResult(
            task_id=task_id,
            status="pending",
            result=None,
            error=None,
            retry_count=0,
        )

        self._tasks[task_id] = task_result

        logger.debug(
            "task_enqueued",
            task_id=task_id,
            task_name=task_name,
            priority=priority,
        )

        return task_id

    async def get_task_status(self, task_id: str) -> QueueTaskResult | None:
        """
        Get task status from in-memory storage
        """
        return self._tasks.get(task_id)

    async def retry_task(self, task_id: str) -> None:
        """
        Retry a failed task
        """
        task = self._tasks.get(task_id)
        if task:
            task.retry_count += 1
            task.status = "retry"
            logger.debug("task_retried", task_id=task_id, retry_count=task.retry_count)

    async def move_to_dlq(self, task_id: str, reason: str) -> None:
        """
        Move task to DLQ
        """
        task = self._tasks.get(task_id)
        if task:
            task.status = "dlq"
            task.error = reason
            self._dlq[task_id] = task
            logger.warning("task_moved_to_dlq", task_id=task_id, reason=reason)

    async def get_dlq_tasks(self, limit: int = 100) -> list[QueueTaskResult]:
        """
        Get DLQ tasks
        """
        return list(self._dlq.values())[:limit]
