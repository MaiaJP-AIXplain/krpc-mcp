"""Smoke tests: server builds and bridge discovers tools via a mocked kRPC connection."""

import logging
from types import SimpleNamespace
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


def test_bridge_invoke_class_setter_with_qualified_class_name():
    """Bridge resolves qualified class names like SpaceCenter.Control."""
    mock_conn = MagicMock()
    services = _make_mock_services()
    services.services[0].procedures[3].parameters[0].type.name = "SpaceCenter.Control"
    mock_conn.krpc.get_services.return_value = services

    mock_control = MagicMock()
    ControlCls = MagicMock(return_value=mock_control)
    type(mock_conn.space_center).Control = ControlCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_control_set_throttle", {"this": 11, "value": 0.25})

    ControlCls.assert_called_once_with(11, mock_conn)
    assert mock_control.throttle == 0.25
    assert result[0].text == "OK"


def test_bridge_invoke_class_setter_with_missing_this_type_name():
    """Bridge infers class name from procedure prefix when this.type.name is missing."""
    mock_conn = MagicMock()
    services = _make_mock_services()
    services.services[0].procedures[3].parameters[0].type.name = ""
    mock_conn.krpc.get_services.return_value = services

    mock_control = MagicMock()
    ControlCls = MagicMock(return_value=mock_control)
    type(mock_conn.space_center).Control = ControlCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_control_set_throttle", {"this": 12, "value": 0.33})

    ControlCls.assert_called_once_with(12, mock_conn)
    assert mock_control.throttle == 0.33
    assert result[0].text == "OK"


def test_bridge_invoke_class_setter_case_insensitive_class_lookup():
    """Bridge resolves class names case-insensitively when schema casing differs."""
    mock_conn = MagicMock()
    services = _make_mock_services()
    services.services[0].procedures[3].parameters[0].type.name = "control"
    mock_conn.krpc.get_services.return_value = services

    mock_control = MagicMock()
    ControlCls = MagicMock(return_value=mock_control)
    type(mock_conn.space_center).Control = ControlCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_control_set_throttle", {"this": 13, "value": 0.44})

    ControlCls.assert_called_once_with(13, mock_conn)
    assert mock_control.throttle == 0.44
    assert result[0].text == "OK"


def test_server_builds():
    """Server builds without errors using a mocked kRPC connection."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.server import build_server
        server = build_server()

    assert server is not None


# ---------------------------------------------------------------------------
# Logging and timing tests
# ---------------------------------------------------------------------------

def test_call_tool_debug_logs_entry_and_exit(caplog):
    """call_tool emits DEBUG lines with tool name and elapsed ms on success."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.warp_to.return_value = None

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            bridge.call_tool("space_center_warp_to", {"ut": 1.0})

    messages = [r.message for r in caplog.records]
    entry = next((m for m in messages if "call_tool space_center_warp_to" in m and "args=" in m), None)
    exit_ = next((m for m in messages if "call_tool space_center_warp_to" in m and "elapsed=" in m), None)
    assert entry is not None, "Expected DEBUG entry log"
    assert exit_ is not None, "Expected DEBUG exit log with elapsed"
    assert "elapsed=" in exit_
    assert "ms" in exit_


def test_call_tool_debug_logs_arg_keys_not_values(caplog):
    """Entry log includes argument key names but not their values."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.warp_to.return_value = None

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            bridge.call_tool("space_center_warp_to", {"ut": 99999.0})

    entry = next(
        r.message for r in caplog.records
        if "call_tool space_center_warp_to" in r.message and "args=" in r.message
    )
    assert "ut" in entry
    assert "99999" not in entry


def test_call_tool_value_error_logs_warning(caplog):
    """ValueError raised during invocation logs at WARNING and includes tool name in response."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    VesselCls = MagicMock(side_effect=ValueError("instance_id must be int"))
    type(mock_conn.space_center).Vessel = VesselCls

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            result = bridge.call_tool("space_center_vessel_get_name", {"this": "notanint"})

    warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("space_center_vessel_get_name" in r.message for r in warn_records)
    assert "[space_center_vessel_get_name]" in result[0].text
    assert "bad input" in result[0].text


def test_call_tool_rpc_error_logs_error(caplog):
    """krpc.error.RPCError logs at ERROR and includes tool name in response."""
    import krpc.error

    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.warp_to.side_effect = krpc.error.RPCError("connection reset")

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            result = bridge.call_tool("space_center_warp_to", {"ut": 0.0})

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("space_center_warp_to" in r.message for r in error_records)
    assert "[space_center_warp_to]" in result[0].text
    assert "kRPC RPC error" in result[0].text


def test_call_tool_unexpected_error_logs_exception(caplog):
    """Unhandled exceptions log at ERROR with traceback and include tool name in response."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.warp_to.side_effect = RuntimeError("internal fault")

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            result = bridge.call_tool("space_center_warp_to", {"ut": 0.0})

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("space_center_warp_to" in r.message for r in error_records)
    assert "[space_center_warp_to]" in result[0].text
    assert "kRPC error" in result[0].text


# ---------------------------------------------------------------------------
# Discovery diagnostic tests (KER-36)
# ---------------------------------------------------------------------------

def test_discovery_logs_skipped_procedure_at_debug(caplog):
    """Each skipped procedure is logged at DEBUG with the skip reason."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            bridge = KrpcBridge()
            bridge.list_tools()  # triggers discovery

    skip_records = [r for r in caplog.records if "Skipping" in r.message]
    assert len(skip_records) == 1, "Expected exactly one skipped procedure log"
    assert "some_stream_proc" in skip_records[0].message
    assert "TC_STREAM" in skip_records[0].message


def test_discovery_logs_per_service_breakdown_at_debug(caplog):
    """Per-service tool counts are logged at DEBUG after discovery."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            bridge = KrpcBridge()
            bridge.list_tools()

    breakdown = next(
        (r.message for r in caplog.records if "per-service counts" in r.message), None
    )
    assert breakdown is not None, "Expected per-service breakdown log"
    assert "SpaceCenter" in breakdown
    assert "tools" in breakdown


def test_discovery_info_log_includes_skipped_count(caplog):
    """The INFO summary log includes both the registered and skipped counts."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        with caplog.at_level(logging.INFO, logger="krpc_mcp.bridge"):
            bridge = KrpcBridge()
            bridge.list_tools()

    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    summary = next((r.message for r in info_records if "registered" in r.message), None)
    assert summary is not None
    assert "skipped" in summary
    # 4 registered, 1 skipped
    assert "4" in summary
    assert "1" in summary


def test_discovery_tolerates_param_without_documentation_field():
    """Discovery should not crash when a parameter omits the optional documentation field."""
    mock_conn = MagicMock()
    services = _make_mock_services()
    # Simulate kRPC metadata where a parameter object has no `documentation` attribute.
    services.services[0].procedures[1].parameters[0] = SimpleNamespace(
        name="ut",
        type=_make_type(1),
        default_value=b"",
    )
    mock_conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge

        bridge = KrpcBridge()
        tools = bridge.list_tools()

    names = {t.name for t in tools}
    assert "space_center_warp_to" in names


def test_discovery_tolerates_proc_without_documentation_field():
    """Discovery should not crash when a procedure omits the optional documentation field."""
    mock_conn = MagicMock()
    services = _make_mock_services()
    proc = services.services[0].procedures[1]
    services.services[0].procedures[1] = SimpleNamespace(
        name=proc.name,
        return_type=proc.return_type,
        parameters=proc.parameters,
    )
    mock_conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge

        bridge = KrpcBridge()
        tools = bridge.list_tools()

    names = {t.name for t in tools}
    assert "space_center_warp_to" in names
