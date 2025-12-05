"""
MCP Server Implementation
Exposes KHW tools to Claude desktop/web
"""

from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent

from app.mcp.tools import (
    create_consultation_tool,
    search_consultations_tool,
    generate_manual_draft_tool,
    search_manuals_tool,
    list_review_tasks_tool,
    approve_review_task_tool,
    reject_review_task_tool,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_mcp_server() -> Server:
    """
    Create MCP server with KHW tools

    Returns:
        MCP Server instance with registered tools
    """
    server = Server("khw-mcp-server")

    logger.info("mcp_server_creating")

    # Register tools
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """
        List all available KHW tools

        Returns:
            List of MCP tools
        """
        return [
            Tool(
                name="create_consultation",
                description="Create a new customer consultation record. Saves to database and indexes for similarity search.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Brief summary of the consultation",
                        },
                        "inquiry_text": {
                            "type": "string",
                            "description": "Customer's inquiry or question",
                        },
                        "action_taken": {
                            "type": "string",
                            "description": "Actions taken to resolve the issue",
                        },
                        "branch_code": {
                            "type": "string",
                            "description": "Branch code where consultation occurred",
                        },
                        "employee_id": {
                            "type": "string",
                            "description": "Employee ID who handled the consultation",
                        },
                        "business_type": {
                            "type": "string",
                            "description": "Business type (e.g., card, loan)",
                        },
                        "error_code": {
                            "type": "string",
                            "description": "Error code if applicable",
                        },
                    },
                    "required": ["summary", "inquiry_text", "action_taken", "branch_code", "employee_id"],
                },
            ),
            Tool(
                name="search_consultations",
                description="Search for similar consultations using semantic similarity. Returns consultations related to the query with similarity scores.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text",
                        },
                        "top_k": {
                            "type": "number",
                            "description": "Number of results to return (default: 10)",
                            "default": 10,
                        },
                        "branch_code": {
                            "type": "string",
                            "description": "Filter by branch code",
                        },
                        "business_type": {
                            "type": "string",
                            "description": "Filter by business type",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="generate_manual_draft",
                description="Generate a manual entry draft from a consultation using LLM. Extracts keywords and creates structured manual content.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "consultation_id": {
                            "type": "string",
                            "description": "UUID of the consultation to generate manual from",
                        },
                    },
                    "required": ["consultation_id"],
                },
            ),
            Tool(
                name="search_manuals",
                description="Search for manual entries using semantic similarity. Returns relevant manual entries with similarity scores.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query text",
                        },
                        "top_k": {
                            "type": "number",
                            "description": "Number of results to return (default: 10)",
                            "default": 10,
                        },
                        "status": {
                            "type": "string",
                            "description": "Filter by status (DRAFT, APPROVED, DEPRECATED)",
                            "enum": ["DRAFT", "APPROVED", "DEPRECATED"],
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="list_review_tasks",
                description="List manual review tasks that need attention. Shows tasks pending approval or rejection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status (TODO, IN_PROGRESS, DONE, REJECTED)",
                            "enum": ["TODO", "IN_PROGRESS", "DONE", "REJECTED"],
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of tasks to return (default: 100)",
                            "default": 100,
                        },
                    },
                },
            ),
            Tool(
                name="approve_review_task",
                description="Approve a manual review task. Updates manual status and creates new version if requested.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "UUID of the review task to approve",
                        },
                        "reviewer_id": {
                            "type": "string",
                            "description": "UUID of the reviewer",
                        },
                        "create_new_version": {
                            "type": "boolean",
                            "description": "Whether to create a new manual version (default: true)",
                            "default": True,
                        },
                    },
                    "required": ["task_id", "reviewer_id"],
                },
            ),
            Tool(
                name="reject_review_task",
                description="Reject a manual review task with a reason. Marks task as rejected.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "UUID of the review task to reject",
                        },
                        "reviewer_id": {
                            "type": "string",
                            "description": "UUID of the reviewer",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Reason for rejection",
                        },
                    },
                    "required": ["task_id", "reviewer_id", "reason"],
                },
            ),
        ]

    # Tool call handlers
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """
        Handle tool calls from Claude

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            List of text content responses
        """
        logger.info("mcp_tool_called", tool_name=name, arguments=arguments)

        try:
            if name == "create_consultation":
                result = await create_consultation_tool(**arguments)
            elif name == "search_consultations":
                result = await search_consultations_tool(**arguments)
            elif name == "generate_manual_draft":
                result = await generate_manual_draft_tool(**arguments)
            elif name == "search_manuals":
                result = await search_manuals_tool(**arguments)
            elif name == "list_review_tasks":
                result = await list_review_tasks_tool(**arguments)
            elif name == "approve_review_task":
                result = await approve_review_task_tool(**arguments)
            elif name == "reject_review_task":
                result = await reject_review_task_tool(**arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

            return [TextContent(type="text", text=result)]

        except Exception as e:
            logger.error("mcp_tool_error", tool_name=name, error=str(e))
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    logger.info("mcp_server_created", tools_count=7)

    return server
