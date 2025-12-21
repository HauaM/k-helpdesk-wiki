from __future__ import annotations

from typing import Sequence
from uuid import UUID

from app.core.exceptions import AuthorizationError
from app.models.task import ManualReviewTask
from app.models.user import User, UserRole
from app.repositories.task_repository import TaskFilter


def get_user_department_ids(user: User) -> list[UUID]:
    """사용자가 속한 부서 ID 목록을 반환."""
    department_links = getattr(user, "department_links", None)
    if not department_links:
        return []
    return [link.department_id for link in department_links if link.department_id]


def ensure_user_can_list_tasks(user: User) -> None:
    """검토 태스크 목록 조회 권한을 확인한다."""
    if user.role == UserRole.ADMIN:
        return
    if user.role == UserRole.REVIEWER:
        if get_user_department_ids(user):
            return
        raise AuthorizationError("소속 부서 정보가 없어 태스크를 조회할 수 없습니다.")
    raise AuthorizationError("검토 태스크를 조회할 수 있는 권한이 없습니다.")


def task_list_filter_for_user(user: User) -> TaskFilter:
    """현재 사용자 기준으로 태스크 조회 필터를 생성한다."""
    if user.role == UserRole.ADMIN:
        return TaskFilter()
    department_ids = get_user_department_ids(user)
    return TaskFilter(reviewer_department_ids=department_ids or None)


def ensure_user_can_access_task(user: User, task: ManualReviewTask) -> None:
    """단일 태스크에 대한 접근 권한을 확인한다."""
    if user.role == UserRole.ADMIN:
        return
    if user.role != UserRole.REVIEWER:
        raise AuthorizationError("검토 태스크에 접근할 권한이 없습니다.")
    department_ids = get_user_department_ids(user)
    if not department_ids or task.reviewer_department_id not in department_ids:
        raise AuthorizationError("해당 태스크를 조회할 권한이 없습니다.")


def filter_tasks_for_user(user: User, tasks: Sequence[ManualReviewTask]) -> list[ManualReviewTask]:
    """사용자별로 보여줄 수 있는 태스크만 필터하여 반환한다."""
    if user.role == UserRole.ADMIN:
        return list(tasks)
    department_ids = get_user_department_ids(user)
    if not department_ids:
        return []
    return [task for task in tasks if task.reviewer_department_id in department_ids]


def ensure_user_can_modify_task(user: User, task: ManualReviewTask) -> None:
    """승인/거절/시작처럼 상태 변경 시 접근을 확인한다."""
    ensure_user_can_access_task(user, task)
