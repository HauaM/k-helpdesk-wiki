"""
Queue Protocol (Interface)
Defines contract for queue implementations
"""

from typing import Protocol, Any, Callable
from datetime import datetime


class QueueTaskResult:
    """
    Result of a queue task execution
    """

    def __init__(
        self,
        task_id: str,
        status: str,  # "success", "failed", "retry", "dlq"
        result: Any = None,
        error: str | None = None,
        retry_count: int = 0,
    ):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.retry_count = retry_count


class QueueProtocol(Protocol):
    """
    Protocol for queue implementations

    RFP Reference: Retry Queue / DLQ for VectorStore and LLM operations
    """

    async def enqueue(
        self,
        task_name: str,
        task_data: dict,
        priority: int = 0,
    ) -> str:
        """
        Enqueue a task for background processing

        Args:
            task_name: Name of the task to execute
            task_data: Task parameters as dict
            priority: Task priority (higher = more important)

        Returns:
            Task ID

        Raises:
            QueueError: If enqueue fails
        """
        ...

    async def get_task_status(self, task_id: str) -> QueueTaskResult | None:
        """
        Get status of a task

        Args:
            task_id: Task ID

        Returns:
            Task result or None if not found
        """
        ...

    async def retry_task(self, task_id: str) -> None:
        """
        Manually retry a failed task

        Args:
            task_id: Task ID to retry

        Raises:
            QueueError: If retry fails
        """
        ...

    async def move_to_dlq(self, task_id: str, reason: str) -> None:
        """
        Move task to Dead Letter Queue

        Args:
            task_id: Task ID
            reason: Reason for moving to DLQ

        Raises:
            QueueError: If operation fails
        """
        ...

    async def get_dlq_tasks(self, limit: int = 100) -> list[QueueTaskResult]:
        """
        Get tasks in Dead Letter Queue

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of DLQ tasks
        """
        ...
