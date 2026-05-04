"""kRPC MCP server entry point."""

import asyncio
import logging
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .tools import (
    register_vessel_tools,
    register_flight_tools,
    register_orbit_tools,
    register_resource_tools,
)
from .connection import close_connection

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def build_server() -> Server:
    server = Server("krpc-mcp")

    register_vessel_tools(server)
    register_flight_tools(server)
    register_orbit_tools(server)
    register_resource_tools(server)

    return server


async def _run() -> None:
    server = build_server()
    logger.info("krpc-mcp server starting on stdio transport")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    try:
        asyncio.run(_run())
    finally:
        close_connection()


if __name__ == "__main__":
    main()
