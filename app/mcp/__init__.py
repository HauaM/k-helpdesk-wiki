"""
MCP Server for KHW
Exposes KHW functionality to Claude via Model Context Protocol
"""

from app.mcp.server import create_mcp_server

__all__ = ["create_mcp_server"]
