"""kRPC MCP server — dynamically exposes the full kRPC API as MCP tools."""

import asyncio
import logging
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server

from .bridge import KrpcBridge
from .connection import close_connection

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)


def build_server() -> Server:
    """Build and return a configured MCP Server backed by the kRPC bridge."""
    server = Server("krpc-mcp")
    KrpcBridge().attach(server)
    return server


async def _run() -> None:
    server = build_server()
    logger.info("krpc-mcp: stdio transport ready (kRPC connection deferred to first tool call)")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    try:
        asyncio.run(_run())
    finally:
        close_connection()


if __name__ == "__main__":
    main()
