"""Smoke tests: server builds and bridge discovers tools via a mocked kRPC connection."""

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers to build a minimal mock kRPC Services protobuf
# ---------------------------------------------------------------------------

def _make_type(code, service="", name="", types=None):
    t = MagicMock()
    t.code = code
    t.service = service
    t.name = name
    t.types = types or []
    return t


def _make_param(pname, type_code, service="", name="", default_value=b""):
    p = MagicMock()
    p.name = pname
    p.type = _make_type(type_code, service, name)
    p.default_value = default_value
    p.documentation = ""
    return p


def _make_proc(pname, params=None, return_code=0, return_service="", return_name="", doc=""):
    proc = MagicMock()
    proc.name = pname
    proc.parameters = params or []
    proc.return_type = _make_type(return_code, return_service, return_name)
    proc.documentation = doc
    return proc


def _make_mock_services():
    """Minimal kRPC service schema covering service-level and class-member procedures."""
    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        # Service-level getter — returns a CLASS (Vessel ID)
        _make_proc("get_ActiveVessel", return_code=100, return_service="SpaceCenter", return_name="Vessel"),
        # Service-level method with a numeric param
        _make_proc("WarpTo", params=[_make_param("ut", 1)]),  # TC_DOUBLE=1
        # Class member getter (this param) — returns STRING
        _make_proc(
            "Vessel_get_Name",
            params=[_make_param("this", 100, "SpaceCenter", "Vessel")],
            return_code=8,  # TC_STRING
        ),
        # Class member setter (this + value)
        _make_proc(
            "Control_set_Throttle",
            params=[
                _make_param("this", 100, "SpaceCenter", "Control"),
                _make_param("value", 1),  # TC_DOUBLE
            ],
        ),
        # Should be skipped — STREAM return type (202)
        _make_proc("some_stream_proc", return_code=202),
    ]

    services = MagicMock()
    services.services = [sc]
    return services


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bridge_discovers_expected_tools():
    """Bridge registers one MCP tool per non-skipped kRPC procedure."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        tools = bridge.list_tools()

    names = {t.name for t in tools}
    assert "space_center_get_active_vessel" in names
    assert "space_center_warp_to" in names
    assert "space_center_vessel_get_name" in names
    assert "space_center_control_set_throttle" in names
    # Skipped because return type is STREAM
    assert "space_center_some_stream_proc" not in names


def test_bridge_input_schema_this_param():
    """Class-member tools include 'this' as a required integer field."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        tools = {t.name: t for t in bridge.list_tools()}

    schema = tools["space_center_vessel_get_name"].inputSchema
    assert schema["properties"]["this"]["type"] == "integer"
    assert "this" in schema["required"]


def test_bridge_invoke_service_method():
    """Bridge correctly invokes a service-level method."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.warp_to.return_value = None

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_warp_to", {"ut": 12345.0})

    mock_conn.space_center.warp_to.assert_called_once_with(ut=12345.0)
    assert result[0].text == "OK"


def test_bridge_invoke_class_getter():
    """Bridge reconstructs a class proxy and reads a property."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    # Simulate the nested Vessel class on the SpaceCenter type
    mock_vessel = MagicMock()
    mock_vessel.name = "Kerbal X"

    VesselCls = MagicMock(return_value=mock_vessel)
    type(mock_conn.space_center).Vessel = VesselCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_vessel_get_name", {"this": 42})

    VesselCls.assert_called_once_with(42, mock_conn)
    assert result[0].text == "Kerbal X"


def test_bridge_invoke_class_setter():
    """Bridge reconstructs a class proxy and sets a property."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    mock_control = MagicMock()
    ControlCls = MagicMock(return_value=mock_control)
    type(mock_conn.space_center).Control = ControlCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_control_set_throttle", {"this": 7, "value": 0.75})

    ControlCls.assert_called_once_with(7, mock_conn)
    assert mock_control.throttle == 0.75
    assert result[0].text == "OK"


def test_server_builds():
    """Server builds without errors using a mocked kRPC connection."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.server import build_server
        server = build_server()

    assert server is not None
