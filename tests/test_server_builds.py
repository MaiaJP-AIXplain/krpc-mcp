"""Smoke tests: server builds and bridge discovers tools via a mocked kRPC connection."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ._helpers import build_proxy

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
        _make_proc(
            "get_ActiveVessel",
            return_code=100,
            return_service="SpaceCenter",
            return_name="Vessel",
        ),
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


def _this(service, class_name):
    return _make_param("this", 100, service, class_name)


def _class_proc(service, pname, params=None, class_name=""):
    return _make_proc(
        pname,
        params=params,
        return_code=100,
        return_service=service,
        return_name=class_name,
    )


def _make_agent_mission_services():
    """Schema covering target bodies plus interplanetary MechJeb planner tools."""
    space_center = MagicMock()
    space_center.name = "SpaceCenter"
    space_center.procedures = [
        _make_proc(
            "get_ActiveVessel",
            return_code=100,
            return_service="SpaceCenter",
            return_name="Vessel",
        ),
        _make_proc("get_Bodies", return_code=303),
        _make_proc(
            "set_TargetBody",
            params=[_make_param("value", 100, "SpaceCenter", "CelestialBody")],
        ),
        _make_proc(
            "CelestialBody_get_Name",
            params=[_this("SpaceCenter", "CelestialBody")],
            return_code=8,
        ),
        _make_proc("Vessel_Recover"),
    ]

    mech_jeb = MagicMock()
    mech_jeb.name = "MechJeb"
    mech_jeb.procedures = [
        _make_proc("get_APIReady", return_code=7),
        _class_proc("MechJeb", "get_ManeuverPlanner", class_name="ManeuverPlanner"),
        _class_proc("MechJeb", "get_NodeExecutor", class_name="NodeExecutor"),
        _class_proc(
            "MechJeb",
            "ManeuverPlanner_get_OperationInterplanetaryTransfer",
            params=[_this("MechJeb", "ManeuverPlanner")],
            class_name="OperationInterplanetaryTransfer",
        ),
        _class_proc(
            "MechJeb",
            "ManeuverPlanner_get_OperationCourseCorrection",
            params=[_this("MechJeb", "ManeuverPlanner")],
            class_name="OperationCourseCorrection",
        ),
        _make_proc(
            "OperationInterplanetaryTransfer_set_WaitForPhaseAngle",
            params=[_this("MechJeb", "OperationInterplanetaryTransfer"), _make_param("value", 7)],
        ),
        _make_proc(
            "OperationInterplanetaryTransfer_MakeNodes",
            params=[_this("MechJeb", "OperationInterplanetaryTransfer")],
            return_code=301,
        ),
        _make_proc(
            "OperationCourseCorrection_set_CourseCorrectFinalPeA",
            params=[_this("MechJeb", "OperationCourseCorrection"), _make_param("value", 1)],
        ),
        _make_proc(
            "OperationCourseCorrection_MakeNodes",
            params=[_this("MechJeb", "OperationCourseCorrection")],
            return_code=301,
        ),
        _make_proc(
            "NodeExecutor_set_Autowarp",
            params=[_this("MechJeb", "NodeExecutor"), _make_param("value", 7)],
        ),
        _make_proc("NodeExecutor_ExecuteOneNode", params=[_this("MechJeb", "NodeExecutor")]),
    ]

    services = MagicMock()
    services.services = [space_center, mech_jeb]
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
    assert "mission_assist_flight_snapshot" in names
    # Skipped because return type is STREAM
    assert "space_center_some_stream_proc" not in names


def test_default_discovery_hides_nonessential_tools():
    """Default mode exposes the curated copilot surface, not every kRPC procedure."""
    services = _make_mock_services()
    services.services[0].procedures.append(_make_proc("Vessel_Recover"))
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}

    assert "space_center_vessel_recover" not in names


def test_full_tool_mode_exposes_all_supported_krpc_tools():
    """KRPC_MCP_TOOL_MODE=full is an escape hatch for low-level debugging."""
    services = _make_mock_services()
    services.services[0].procedures.append(_make_proc("Vessel_Recover"))
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = services

    with patch.dict("os.environ", {"KRPC_MCP_TOOL_MODE": "full"}, clear=False):
        with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
            from krpc_mcp.bridge import KrpcBridge
            names = {t.name for t in KrpcBridge().list_tools()}

    assert "space_center_vessel_recover" in names
    assert "mission_assist_flight_snapshot" in names


def test_curated_surface_includes_agent_interplanetary_tools():
    """Agent-scale goals need target bodies, transfer planning, corrections, and executor warp."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_agent_mission_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}

    assert "space_center_get_bodies" in names
    assert "space_center_set_target_body" in names
    assert "space_center_celestial_body_get_name" in names
    assert "mech_jeb_maneuver_planner_get_operation_interplanetary_transfer" in names
    assert "mech_jeb_operation_interplanetary_transfer_set_wait_for_phase_angle" in names
    assert "mech_jeb_operation_interplanetary_transfer_make_nodes" in names
    assert "mech_jeb_maneuver_planner_get_operation_course_correction" in names
    assert "mech_jeb_operation_course_correction_set_course_correct_final_pe_a" in names
    assert "mech_jeb_operation_course_correction_make_nodes" in names
    assert "mech_jeb_node_executor_set_autowarp" in names
    assert "mech_jeb_node_executor_execute_one_node" in names
    assert "mission_assist_plan_goal" in names
    assert "space_center_vessel_recover" not in names


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


def test_bridge_invoke_class_getter(kspc_env):
    """Bridge reconstructs a class proxy and reads a property."""
    instances: list = []
    kspc_env.module.Vessel = build_proxy(
        "Vessel", properties={"name": "Kerbal X"}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool("space_center_vessel_get_name", {"this": 42})

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 42)
    assert result[0].text == "Kerbal X"


def test_bridge_invoke_class_setter(kspc_env):
    """Bridge reconstructs a class proxy and sets a property."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"throttle": None}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "space_center_control_set_throttle", {"this": 7, "value": 0.75}
        )

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 7)
    assert instances[0].throttle == 0.75
    assert result[0].text == "OK"


def test_bridge_invoke_class_setter_with_qualified_class_name(kspc_env):
    """Bridge resolves qualified class names like SpaceCenter.Control to the leaf."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"throttle": None}, instances=instances
    )
    services = _make_mock_services()
    services.services[0].procedures[3].parameters[0].type.name = "SpaceCenter.Control"
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "space_center_control_set_throttle", {"this": 11, "value": 0.25}
        )

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 11)
    assert instances[0].throttle == 0.25
    assert result[0].text == "OK"


def test_bridge_invoke_class_setter_with_missing_this_type_name(kspc_env):
    """Bridge infers class name from procedure prefix when this.type.name is missing."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"throttle": None}, instances=instances
    )
    services = _make_mock_services()
    services.services[0].procedures[3].parameters[0].type.name = ""
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "space_center_control_set_throttle", {"this": 12, "value": 0.33}
        )

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 12)
    assert instances[0].throttle == 0.33
    assert result[0].text == "OK"


def test_bridge_class_proxy_error_includes_handle_guidance(kspc_env):
    """Missing class → error text helps callers thread the right handle.

    The hint exists because callers commonly pass a Vessel handle into
    Control_* tools by mistake; the error needs to point them at the
    Vessel_get_Control -> Control_* chain.
    """
    # Intentionally do NOT register Control on the module.
    kspc_env.conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "space_center_control_set_throttle", {"this": 32, "value": 0.1}
        )

    text = result[0].text
    assert "Control" in text
    assert "handle" in text.lower()
    assert "Vessel_get_Control" in text


def test_bridge_read_only_mode_blocks_mutating_calls():
    """Read-only mode blocks mutating procedures such as set_ operations."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        with patch.dict("os.environ", {"KRPC_MCP_READ_ONLY": "1"}, clear=False):
            from krpc_mcp.bridge import KrpcBridge
            bridge = KrpcBridge()
            result = bridge.call_tool(
                "space_center_control_set_throttle", {"this": 7, "value": 0.1}
            )

    assert "blocked by read-only mode" in result[0].text


def test_bridge_read_only_mode_allows_getters():
    """Read-only mode still allows non-mutating get_ calls."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        with patch.dict("os.environ", {"KRPC_MCP_READ_ONLY": "1"}, clear=False):
            from krpc_mcp.bridge import KrpcBridge
            bridge = KrpcBridge()
            result = bridge.call_tool("space_center_get_active_vessel", {})

    assert "blocked by read-only mode" not in result[0].text


def test_mission_assist_flight_snapshot_returns_copilot_state():
    """Mission assist collapses common vessel, flight, orbit, and handle reads into one tool."""

    class Obj:
        def __init__(self, object_id=None, **attrs):
            if object_id is not None:
                self._object_id = object_id
            for key, value in attrs.items():
                setattr(self, key, value)

    control = Obj(2, throttle=0.5, sas=True, sas_mode=0, rcs=False, gear=False, brakes=False)
    flight = Obj(
        3,
        altitude=1200.0,
        mean_altitude=1250.0,
        surface_altitude=300.0,
        latitude=-0.1,
        longitude=-74.5,
        speed=250.0,
        vertical_speed=12.0,
        horizontal_speed=240.0,
        heading=90.0,
        pitch=10.0,
        roll=0.0,
        g_force=1.2,
    )
    orbit = Obj(
        4,
        apoapsis_altitude=100000.0,
        periapsis_altitude=80000.0,
        eccentricity=0.01,
        inclination=0.0,
        period=3600.0,
        time_to_apoapsis=120.0,
        time_to_periapsis=1920.0,
        semi_major_axis=700000.0,
        orbital_speed=2200.0,
    )
    resources = Obj(5, names=["LiquidFuel", "Oxidizer"])
    vessel = Obj(
        1,
        name="Kerbal X",
        met=42.0,
        mass=12.5,
        situation=3,
        control=control,
        flight=flight,
        orbit=orbit,
        resources=resources,
    )

    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_mock_services()
    mock_conn.space_center.active_vessel = vessel
    mock_conn.mech_jeb.api_ready = True

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("mission_assist_flight_snapshot", {})

    payload = json.loads(result[0].text)
    assert payload["active_vessel"]["name"] == "Kerbal X"
    assert payload["handles"] == {
        "vessel": 1,
        "control": 2,
        "flight": 3,
        "orbit": 4,
        "resources": 5,
    }
    assert payload["control"]["throttle"] == 0.5
    assert payload["flight"]["altitude"] == 1200.0
    assert payload["orbit"]["apoapsis_altitude"] == 100000.0
    assert payload["resources"]["names"] == ["LiquidFuel", "Oxidizer"]
    assert payload["mechjeb"]["api_ready"] is True


def test_mission_assist_plan_goal_returns_duna_landing_playbook():
    """Goal planner gives agents a staged MechJeb-first route for big objectives."""

    class Obj:
        def __init__(self, object_id=None, **attrs):
            if object_id is not None:
                self._object_id = object_id
            for key, value in attrs.items():
                setattr(self, key, value)

    vessel = Obj(
        1,
        name="Hope 1",
        met=42.0,
        mass=12.5,
        situation=3,
        control=Obj(2, throttle=0.0, sas=True, sas_mode=0, rcs=False, gear=False, brakes=False),
        flight=Obj(3, altitude=100000.0),
        orbit=Obj(
            4,
            apoapsis_altitude=120000.0,
            periapsis_altitude=100000.0,
            eccentricity=0.01,
            inclination=0.0,
            period=3600.0,
            time_to_apoapsis=120.0,
            time_to_periapsis=1920.0,
            semi_major_axis=700000.0,
            orbital_speed=2200.0,
        ),
        resources=Obj(5, names=["LiquidFuel", "Oxidizer"]),
    )
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_agent_mission_services()
    mock_conn.space_center.active_vessel = vessel
    mock_conn.mech_jeb.api_ready = True

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "mission_assist_plan_goal",
            {"objective": "land this vessel on Duna"},
        )

    payload = json.loads(result[0].text)
    phase_names = [phase["name"] for phase in payload["phases"]]
    assert payload["destination_body"] == "Duna"
    assert payload["strategy"] == "mechjeb_first"
    assert payload["defaults"]["warp_long_waits"] is True
    assert payload["defaults"]["prefer_node_executor_autowarp"] is True
    assert "interplanetary_transfer" in phase_names
    assert "midcourse_correction" in phase_names
    assert "arrival_capture" in phase_names
    assert "descent_and_landing" in phase_names
    tools = {tool for phase in payload["phases"] for tool in phase["tools"]}
    assert "mech_jeb_maneuver_planner_get_operation_interplanetary_transfer" in tools
    assert "mech_jeb_node_executor_set_autowarp" in tools
    assert "space_center_warp_to" not in tools


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
    entry = next(
        (m for m in messages if "call_tool space_center_warp_to" in m and "args=" in m),
        None,
    )
    exit_ = next(
        (m for m in messages if "call_tool space_center_warp_to" in m and "elapsed=" in m),
        None,
    )
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


def test_call_tool_value_error_logs_warning(caplog, kspc_env):
    """ValueError raised during invocation logs at WARNING and includes tool name in response."""

    class _BoomVessel:
        def __init__(self, client, object_id):
            raise ValueError("instance_id must be int")

    kspc_env.module.Vessel = _BoomVessel
    kspc_env.conn.krpc.get_services.return_value = _make_mock_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        with caplog.at_level(logging.DEBUG, logger="krpc_mcp.bridge"):
            result = bridge.call_tool(
                "space_center_vessel_get_name", {"this": "notanint"}
            )

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
    # 4 kRPC tools + 2 mission-assist tools registered, 1 skipped
    assert "6" in summary
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
