"""Smoke test: server builds without errors (no KSP connection required)."""

import pytest
from unittest.mock import patch, MagicMock


def test_server_registers_all_tools():
    """Server builds and registers tools from all modules without a live kRPC connection."""
    # Patch the krpc module before importing our server so no real connection is attempted
    mock_krpc = MagicMock()
    with patch.dict("sys.modules", {"krpc": mock_krpc}):
        from krpc_mcp.server import build_server
        server = build_server()

    tool_names = [t.name for t in (server.list_tools() or [])]
    assert "get_vessel_info" in tool_names
    assert "set_throttle" in tool_names
    assert "get_orbit_info" in tool_names
    assert "get_resources" in tool_names
