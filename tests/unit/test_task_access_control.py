import pytest
from uuid import UUID, uuid4
from unittest.mock import MagicMock

from app.core.exceptions import AuthorizationError
from app.core.permissions import (
    ensure_user_can_access_task,
    ensure_user_can_list_tasks,
    filter_tasks_for_user,
    get_user_department_ids,
    task_list_filter_for_user,
)
from app.models.user import UserRole


def build_user(role: UserRole, department_ids: list[UUID]) -> MagicMock:
    user = MagicMock()
    user.role = role
    links = []
    primary_id = department_ids[0] if department_ids else None
    for dept_id in department_ids:
        link = MagicMock()
        link.department_id = dept_id
        link.is_primary = dept_id == primary_id
        links.append(link)
    user.department_links = links
    return user


def test_get_user_department_ids_includes_assigned_departments():
    dept_id = uuid4()
    user = build_user(UserRole.REVIEWER, [dept_id])

    assert get_user_department_ids(user) == [dept_id]


def test_task_list_filter_for_admin_is_unrestricted():
    admin = build_user(UserRole.ADMIN, [])

    task_filter = task_list_filter_for_user(admin)

    assert task_filter.reviewer_department_ids is None


def test_task_list_filter_for_reviewer_contains_department_ids():
    dept_ids = [uuid4(), uuid4()]
    reviewer = build_user(UserRole.REVIEWER, dept_ids)

    task_filter = task_list_filter_for_user(reviewer)

    assert task_filter.reviewer_department_ids == dept_ids


def test_ensure_user_can_list_tasks_reviewer_without_department():
    reviewer = build_user(UserRole.REVIEWER, [])

    with pytest.raises(AuthorizationError):
        ensure_user_can_list_tasks(reviewer)


def test_ensure_user_can_access_task_reviewer_wrong_department():
    dept_id = uuid4()
    reviewer = build_user(UserRole.REVIEWER, [dept_id])
    task = MagicMock()
    task.reviewer_department_id = uuid4()

    with pytest.raises(AuthorizationError):
        ensure_user_can_access_task(reviewer, task)


def test_filter_tasks_for_user_returns_only_matching_department():
    dept_a = uuid4()
    dept_b = uuid4()
    reviewer = build_user(UserRole.REVIEWER, [dept_a])
    task_a = MagicMock()
    task_a.reviewer_department_id = dept_a
    task_b = MagicMock()
    task_b.reviewer_department_id = dept_b

    visible = filter_tasks_for_user(reviewer, [task_a, task_b])

    assert visible == [task_a]
