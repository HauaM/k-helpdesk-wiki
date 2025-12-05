#!/usr/bin/env python
"""
MCP Server Entry Point

Run this to start the MCP server for Claude integration:
    python mcp_server.py
"""

import asyncio
from mcp.server.stdio import stdio_server

from app.mcp.server import create_mcp_server
from app.core.logging import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)


async def main():
    """
    Main entry point for MCP server
    """
    logger.info("mcp_server_starting")

    # Create MCP server
    server = create_mcp_server()

    # Run server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        logger.info("mcp_server_running", transport="stdio")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
