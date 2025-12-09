"""
MCP Tool Implementations
Business logic for MCP tool calls
"""

import json
from uuid import UUID
from typing import Any

from app.core.db import async_session_maker
from app.services.consultation import ConsultationService
from app.services.manual_service import ManualService
from app.services.common_code_service import CommonCodeService
from app.vectorstore.factory import get_consultation_vectorstore, get_manual_vectorstore
from app.llm.factory import get_llm_client_instance
from app.core.logging import get_logger
from app.core.exceptions import RecordNotFoundError, DuplicateRecordError

logger = get_logger(__name__)


async def create_consultation_tool(
    summary: str,
    inquiry_text: str,
    action_taken: str,
    branch_code: str,
    employee_id: str,
    business_type: str | None = None,
    error_code: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Create new consultation via MCP

    Args:
        summary: Consultation summary
        inquiry_text: Customer inquiry
        action_taken: Actions taken
        branch_code: Branch code
        employee_id: Employee ID
        business_type: Business type (optional)
        error_code: Error code (optional)
        **kwargs: Additional metadata

    Returns:
        JSON string with consultation details
    """
    logger.info("mcp_create_consultation", branch_code=branch_code)

    async with async_session_maker() as session:
        service = ConsultationService(
            session=session,
            vectorstore=get_consultation_vectorstore(),
            llm_client=get_llm_client_instance(),
        )

        # TODO: Implement when service layer is ready
        # consultation = await service.register_consultation(
        #     summary=summary,
        #     inquiry_text=inquiry_text,
        #     action_taken=action_taken,
        #     branch_code=branch_code,
        #     employee_id=employee_id,
        #     business_type=business_type,
        #     error_code=error_code,
        #     **kwargs,
        # )

        # return json.dumps({
        #     "id": str(consultation.id),
        #     "summary": consultation.summary,
        #     "created_at": consultation.created_at.isoformat(),
        # }, indent=2)

        return json.dumps({
            "status": "not_implemented",
            "message": "Consultation creation service not yet implemented",
            "inputs": {
                "summary": summary,
                "branch_code": branch_code,
                "employee_id": employee_id,
            },
        }, indent=2)


async def search_consultations_tool(
    query: str,
    top_k: int = 10,
    branch_code: str | None = None,
    business_type: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Search consultations via MCP

    Args:
        query: Search query
        top_k: Number of results
        branch_code: Optional branch filter
        business_type: Optional business type filter

    Returns:
        JSON string with search results
    """
    logger.info("mcp_search_consultations", query=query, top_k=top_k)

    async with async_session_maker() as session:
        service = ConsultationService(
            session=session,
            vectorstore=get_consultation_vectorstore(),
            llm_client=get_llm_client_instance(),
        )

        # TODO: Implement when service layer is ready
        # results = await service.search_similar_consultations(
        #     query=query,
        #     top_k=top_k,
        #     branch_code=branch_code,
        #     business_type=business_type,
        # )

        # return json.dumps({
        #     "query": query,
        #     "results": [
        #         {
        #             "id": str(c.id),
        #             "summary": c.summary,
        #             "similarity": score,
        #         }
        #         for c, score in results
        #     ],
        # }, indent=2)

        return json.dumps({
            "status": "not_implemented",
            "message": "Consultation search service not yet implemented",
            "query": query,
        }, indent=2)


async def generate_manual_draft_tool(
    consultation_id: str,
    **kwargs: Any,
) -> str:
    """
    Generate manual draft via MCP

    Args:
        consultation_id: Consultation UUID

    Returns:
        JSON string with manual draft
    """
    logger.info("mcp_generate_manual", consultation_id=consultation_id)

    async with async_session_maker() as session:
        service = ManualService(
            session=session,
            vectorstore=get_manual_vectorstore(),
            llm_client=get_llm_client_instance(),
        )

        # TODO: Implement when service layer is ready
        # manual_draft = await service.generate_manual_draft(
        #     consultation_id=UUID(consultation_id),
        #     ...
        # )

        return json.dumps({
            "status": "not_implemented",
            "message": "Manual draft generation not yet implemented",
            "consultation_id": consultation_id,
        }, indent=2)


async def search_manuals_tool(
    query: str,
    top_k: int = 10,
    status: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Search manuals via MCP

    Args:
        query: Search query
        top_k: Number of results
        status: Optional status filter

    Returns:
        JSON string with search results
    """
    logger.info("mcp_search_manuals", query=query, top_k=top_k)

    return json.dumps({
        "status": "not_implemented",
        "message": "Manual search not yet implemented",
        "query": query,
    }, indent=2)


async def list_review_tasks_tool(
    status: str | None = None,
    limit: int = 100,
    **kwargs: Any,
) -> str:
    """
    List review tasks via MCP

    Args:
        status: Optional status filter
        limit: Maximum results

    Returns:
        JSON string with review tasks
    """
    logger.info("mcp_list_review_tasks", status=status, limit=limit)

    return json.dumps({
        "status": "not_implemented",
        "message": "Review task listing not yet implemented",
    }, indent=2)


async def approve_review_task_tool(
    task_id: str,
    employee_id: str,
    create_new_version: bool = True,
    **kwargs: Any,
) -> str:
    """
    Approve review task via MCP

    Args:
        task_id: Task UUID
        employee_id: Reviewer employee_id
        create_new_version: Create new version flag

    Returns:
        JSON string with result
    """
    logger.info("mcp_approve_task", task_id=task_id, employee_id=employee_id)

    return json.dumps({
        "status": "not_implemented",
        "message": "Review task approval not yet implemented",
        "task_id": task_id,
    }, indent=2)


async def reject_review_task_tool(
    task_id: str,
    employee_id: str,
    reason: str,
    **kwargs: Any,
) -> str:
    """
    Reject review task via MCP

    Args:
        task_id: Task UUID
        employee_id: Reviewer employee_id
        reason: Rejection reason

    Returns:
        JSON string with result
    """
    logger.info("mcp_reject_task", task_id=task_id, employee_id=employee_id)

    return json.dumps({
        "status": "not_implemented",
        "message": "Review task rejection not yet implemented",
        "task_id": task_id,
        "reason": reason,
    }, indent=2)


# ==================== Common Code Management (FR-15) ====================


async def get_common_codes_tool(
    group_code: str,
    **kwargs: Any,
) -> str:
    """
    Retrieve common codes by group code via MCP

    Args:
        group_code: Group code (e.g., BUSINESS_TYPE, ERROR_CODE)
        **kwargs: Additional parameters

    Returns:
        JSON string with common codes
    """
    logger.info("mcp_get_common_codes", group_code=group_code)

    try:
        async with async_session_maker() as session:
            service = CommonCodeService(session=session)
            result = await service.get_codes_by_group_code(group_code, is_active_only=True)

            return json.dumps({
                "status": "success",
                "group_code": result.group_code,
                "items": [
                    {
                        "code_key": item.code_key,
                        "code_value": item.code_value,
                    }
                    for item in result.items
                ],
            }, indent=2)
    except RecordNotFoundError as e:
        return json.dumps({
            "status": "error",
            "error": "not_found",
            "message": str(e),
        }, indent=2)
    except Exception as e:
        logger.error("mcp_get_common_codes_error", error=str(e))
        return json.dumps({
            "status": "error",
            "error": "internal_error",
            "message": str(e),
        }, indent=2)


async def get_multiple_common_codes_tool(
    group_codes: list[str],
    **kwargs: Any,
) -> str:
    """
    Retrieve multiple common code groups via MCP

    Args:
        group_codes: List of group codes
        **kwargs: Additional parameters

    Returns:
        JSON string with multiple common code groups
    """
    logger.info("mcp_get_multiple_common_codes", count=len(group_codes))

    try:
        async with async_session_maker() as session:
            service = CommonCodeService(session=session)
            result = await service.get_multiple_code_groups(group_codes, is_active_only=True)

            return json.dumps({
                "status": "success",
                "data": {
                    group_code: {
                        "group_code": group_code,
                        "items": [
                            {
                                "code_key": item.code_key,
                                "code_value": item.code_value,
                            }
                            for item in group.items
                        ],
                    }
                    for group_code, group in result.data.items()
                },
            }, indent=2)
    except Exception as e:
        logger.error("mcp_get_multiple_common_codes_error", error=str(e))
        return json.dumps({
            "status": "error",
            "error": "internal_error",
            "message": str(e),
        }, indent=2)


async def create_common_code_group_tool(
    group_code: str,
    group_name: str,
    description: str | None = None,
    **kwargs: Any,
) -> str:
    """
    Create new common code group via MCP

    Args:
        group_code: Unique group code
        group_name: Group name
        description: Group description (optional)
        **kwargs: Additional parameters

    Returns:
        JSON string with created group
    """
    logger.info("mcp_create_common_code_group", group_code=group_code)

    try:
        from app.schemas.common_code import CommonCodeGroupCreate

        async with async_session_maker() as session:
            service = CommonCodeService(session=session)

            payload = CommonCodeGroupCreate(
                group_code=group_code,
                group_name=group_name,
                description=description,
            )

            result = await service.create_group(payload)

            return json.dumps({
                "status": "success",
                "id": str(result.id),
                "group_code": result.group_code,
                "group_name": result.group_name,
            }, indent=2)
    except DuplicateRecordError as e:
        return json.dumps({
            "status": "error",
            "error": "duplicate",
            "message": str(e),
        }, indent=2)
    except Exception as e:
        logger.error("mcp_create_common_code_group_error", error=str(e))
        return json.dumps({
            "status": "error",
            "error": "internal_error",
            "message": str(e),
        }, indent=2)


async def create_common_code_item_tool(
    group_code: str,
    code_key: str,
    code_value: str,
    sort_order: int = 0,
    **kwargs: Any,
) -> str:
    """
    Create new common code item via MCP

    Args:
        group_code: Parent group code
        code_key: Code key
        code_value: Code display value
        sort_order: Sort order (optional)
        **kwargs: Additional parameters

    Returns:
        JSON string with created item
    """
    logger.info("mcp_create_common_code_item", group_code=group_code, code_key=code_key)

    try:
        from app.schemas.common_code import CommonCodeItemCreate

        async with async_session_maker() as session:
            service = CommonCodeService(session=session)

            # Get group by code
            group = await service.group_repo.get_by_group_code(group_code)
            if not group:
                raise RecordNotFoundError(f"CommonCodeGroup with code '{group_code}' not found")

            # Create item
            payload = CommonCodeItemCreate(
                code_key=code_key,
                code_value=code_value,
                sort_order=sort_order,
            )

            result = await service.create_item(group.id, payload)

            return json.dumps({
                "status": "success",
                "id": str(result.id),
                "group_id": str(result.group_id),
                "code_key": result.code_key,
                "code_value": result.code_value,
            }, indent=2)
    except RecordNotFoundError as e:
        return json.dumps({
            "status": "error",
            "error": "not_found",
            "message": str(e),
        }, indent=2)
    except DuplicateRecordError as e:
        return json.dumps({
            "status": "error",
            "error": "duplicate",
            "message": str(e),
        }, indent=2)
    except Exception as e:
        logger.error("mcp_create_common_code_item_error", error=str(e))
        return json.dumps({
            "status": "error",
            "error": "internal_error",
            "message": str(e),
        }, indent=2)
