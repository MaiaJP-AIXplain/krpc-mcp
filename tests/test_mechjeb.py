"""Integration tests: kRPC.MechJeb MCP tools via the bridge.

Covers:
- Discovery: all MechJeb service procedures registered as MCP tools
- APIReady guard: blocked when false, passes when true, bypassed for get_APIReady
- OperationException: surfaced as structured MechJeb error response
- Ascent launch: set desired orbit altitude + enable AscentAutopilot
- Circularize + execute: OperationCircularize.MakeNodes() + NodeExecutor.ExecuteOneNode()
- Landing: LandingAutopilot.LandUntargeted()
- Docking approach: DockingAutopilot.Enabled = True
"""

from unittest.mock import MagicMock, patch

import krpc.error

# ---------------------------------------------------------------------------
# Type code constants (mirror type_mapper.py)
# ---------------------------------------------------------------------------
TC_NONE = 0
TC_DOUBLE = 1
TC_FLOAT = 2
TC_BOOL = 7
TC_STRING = 8
TC_CLASS = 100
TC_LIST = 301


# ---------------------------------------------------------------------------
# Mock builder helpers
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


def _make_proc(pname, params=None, return_code=TC_NONE, return_service="", return_name="", doc=""):
    proc = MagicMock()
    proc.name = pname
    proc.parameters = params or []
    proc.return_type = _make_type(return_code, return_service, return_name)
    proc.documentation = doc
    return proc


def _this(class_name):
    return _make_param("this", TC_CLASS, "MechJeb", class_name)


def _mj(pname, params=None, class_name=""):
    """Shorthand for a MechJeb CLASS-returning procedure."""
    return _make_proc(
        pname, params=params,
        return_code=TC_CLASS, return_service="MechJeb", return_name=class_name,
    )


def _make_mechjeb_services():
    """Full mock MechJeb service schema covering autopilots, planner, executor, controllers."""
    svc = MagicMock()
    svc.name = "MechJeb"
    svc.procedures = [
        # Root accessors
        _make_proc("get_APIReady", return_code=TC_BOOL),
        _mj("get_AscentAutopilot", class_name="AscentAutopilot"),
        _mj("get_LandingAutopilot", class_name="LandingAutopilot"),
        _mj("get_DockingAutopilot", class_name="DockingAutopilot"),
        _mj("get_RendezvousAutopilot", class_name="RendezvousAutopilot"),
        _mj("get_NodeExecutor", class_name="NodeExecutor"),
        _mj("get_ManeuverPlanner", class_name="ManeuverPlanner"),
        _mj("get_SmartASS", class_name="SmartASS"),
        _mj("get_ThrustController", class_name="ThrustController"),
        _mj("get_StagingController", class_name="StagingController"),
        _mj("get_RCSController", class_name="RCSController"),

        # AscentAutopilot
        _make_proc("AscentAutopilot_get_Enabled",
                   params=[_this("AscentAutopilot")], return_code=TC_BOOL),
        _make_proc("AscentAutopilot_set_Enabled",
                   params=[_this("AscentAutopilot"), _make_param("value", TC_BOOL)]),
        _make_proc("AscentAutopilot_set_DesiredOrbitAltitude",
                   params=[_this("AscentAutopilot"), _make_param("value", TC_DOUBLE)]),
        _make_proc("AscentAutopilot_set_DesiredInclination",
                   params=[_this("AscentAutopilot"), _make_param("value", TC_DOUBLE)]),
        _make_proc("AscentAutopilot_get_Status",
                   params=[_this("AscentAutopilot")], return_code=TC_STRING),
        _make_proc("AscentAutopilot_LaunchToRendezvous",
                   params=[_this("AscentAutopilot")]),
        _make_proc("AscentAutopilot_LaunchToTargetPlane",
                   params=[_this("AscentAutopilot")]),

        # LandingAutopilot
        _make_proc("LandingAutopilot_get_Enabled",
                   params=[_this("LandingAutopilot")], return_code=TC_BOOL),
        _make_proc("LandingAutopilot_set_Enabled",
                   params=[_this("LandingAutopilot"), _make_param("value", TC_BOOL)]),
        _make_proc("LandingAutopilot_LandUntargeted",
                   params=[_this("LandingAutopilot")]),
        _make_proc("LandingAutopilot_LandAtPositionTarget",
                   params=[_this("LandingAutopilot")]),
        _make_proc("LandingAutopilot_StopLanding",
                   params=[_this("LandingAutopilot")]),
        _make_proc("LandingAutopilot_set_TouchdownSpeed",
                   params=[_this("LandingAutopilot"), _make_param("value", TC_DOUBLE)]),
        _make_proc("LandingAutopilot_get_Status",
                   params=[_this("LandingAutopilot")], return_code=TC_STRING),

        # DockingAutopilot
        _make_proc("DockingAutopilot_get_Enabled",
                   params=[_this("DockingAutopilot")], return_code=TC_BOOL),
        _make_proc("DockingAutopilot_set_Enabled",
                   params=[_this("DockingAutopilot"), _make_param("value", TC_BOOL)]),
        _make_proc("DockingAutopilot_set_SpeedLimit",
                   params=[_this("DockingAutopilot"), _make_param("value", TC_DOUBLE)]),
        _make_proc("DockingAutopilot_get_Status",
                   params=[_this("DockingAutopilot")], return_code=TC_STRING),

        # NodeExecutor
        _make_proc("NodeExecutor_get_Enabled",
                   params=[_this("NodeExecutor")], return_code=TC_BOOL),
        _make_proc("NodeExecutor_set_Autowarp",
                   params=[_this("NodeExecutor"), _make_param("value", TC_BOOL)]),
        _make_proc("NodeExecutor_ExecuteOneNode", params=[_this("NodeExecutor")]),
        _make_proc("NodeExecutor_ExecuteAllNodes", params=[_this("NodeExecutor")]),
        _make_proc("NodeExecutor_Abort", params=[_this("NodeExecutor")]),

        # ManeuverPlanner
        _mj("ManeuverPlanner_get_OperationCircularize",
            params=[_this("ManeuverPlanner")], class_name="OperationCircularize"),
        _mj("ManeuverPlanner_get_OperationApoapsis",
            params=[_this("ManeuverPlanner")], class_name="OperationApoapsis"),
        _mj("ManeuverPlanner_get_OperationPeriapsis",
            params=[_this("ManeuverPlanner")], class_name="OperationPeriapsis"),

        # OperationCircularize
        _make_proc("OperationCircularize_MakeNodes",
                   params=[_this("OperationCircularize")], return_code=TC_LIST),
        _make_proc("OperationCircularize_get_ErrorMessage",
                   params=[_this("OperationCircularize")], return_code=TC_STRING),

        # OperationApoapsis
        _make_proc("OperationApoapsis_MakeNodes",
                   params=[_this("OperationApoapsis")], return_code=TC_LIST),
        _make_proc("OperationApoapsis_set_NewApoapsis",
                   params=[_this("OperationApoapsis"), _make_param("value", TC_DOUBLE)]),

        # SmartASS
        _make_proc("SmartASS_Update",
                   params=[_this("SmartASS"), _make_param("resetPID", TC_BOOL)]),
        _make_proc("SmartASS_get_AutopilotMode",
                   params=[_this("SmartASS")], return_code=TC_STRING),
        _make_proc("SmartASS_set_AutopilotMode",
                   params=[_this("SmartASS"), _make_param("value", TC_STRING)]),

        # ThrustController
        _make_proc("ThrustController_get_Enabled",
                   params=[_this("ThrustController")], return_code=TC_BOOL),
        _make_proc("ThrustController_set_Enabled",
                   params=[_this("ThrustController"), _make_param("value", TC_BOOL)]),
        _make_proc("ThrustController_set_LimitAcceleration",
                   params=[_this("ThrustController"), _make_param("value", TC_BOOL)]),

        # StagingController
        _make_proc("StagingController_get_Enabled",
                   params=[_this("StagingController")], return_code=TC_BOOL),
        _make_proc("StagingController_set_Enabled",
                   params=[_this("StagingController"), _make_param("value", TC_BOOL)]),

        # RCSController
        _make_proc("RCSController_get_Enabled",
                   params=[_this("RCSController")], return_code=TC_BOOL),
        _make_proc("RCSController_set_Enabled",
                   params=[_this("RCSController"), _make_param("value", TC_BOOL)]),
    ]

    services = MagicMock()
    services.services = [svc]
    return services


def _make_conn(api_ready=True):
    """Build a mock kRPC connection with MechJeb API readiness configured."""
    conn = MagicMock()
    conn.krpc.get_services.return_value = _make_mechjeb_services()
    conn.mech_jeb.api_ready = api_ready
    return conn


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------

def test_mechjeb_tools_discovered():
    """Bridge registers MechJeb service procedures as MCP tools."""
    conn = _make_conn()
    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        names = {t.name for t in bridge.list_tools()}

    assert "mech_jeb_get_api_ready" in names
    assert "mech_jeb_get_ascent_autopilot" in names
    assert "mech_jeb_ascent_autopilot_set_enabled" in names
    assert "mech_jeb_ascent_autopilot_set_desired_orbit_altitude" in names
    assert "mech_jeb_landing_autopilot_land_untargeted" in names
    assert "mech_jeb_landing_autopilot_land_at_position_target" in names
    assert "mech_jeb_landing_autopilot_stop_landing" in names
    assert "mech_jeb_docking_autopilot_set_enabled" in names
    assert "mech_jeb_node_executor_execute_one_node" in names
    assert "mech_jeb_node_executor_execute_all_nodes" in names
    assert "mech_jeb_node_executor_abort" in names
    assert "mech_jeb_maneuver_planner_get_operation_circularize" in names
    assert "mech_jeb_operation_circularize_make_nodes" in names
    assert "mech_jeb_smart_ass_update" in names
    assert "mech_jeb_thrust_controller_set_enabled" in names
    assert "mech_jeb_staging_controller_set_enabled" in names
    assert "mech_jeb_rcs_controller_set_enabled" in names


def test_mechjeb_tools_have_this_param_schema():
    """Class-member MechJeb tools require 'this' as an integer field."""
    conn = _make_conn()
    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        tools = {t.name: t for t in bridge.list_tools()}

    schema = tools["mech_jeb_node_executor_execute_one_node"].inputSchema
    assert schema["properties"]["this"]["type"] == "integer"
    assert "this" in schema["required"]


# ---------------------------------------------------------------------------
# APIReady guard tests
# ---------------------------------------------------------------------------

def test_mechjeb_api_not_ready_blocks_tool_call():
    """When APIReady is False, any MechJeb tool call returns an error without invoking kRPC."""
    conn = _make_conn(api_ready=False)
    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 1}
        )

    assert "APIReady" in result[0].text or "not initialised" in result[0].text
    # kRPC procedure must NOT have been invoked
    conn.mech_jeb.execute_one_node.assert_not_called()


def test_mechjeb_api_ready_allows_tool_call():
    """When APIReady is True, the tool call proceeds normally."""
    conn = _make_conn(api_ready=True)

    mock_executor = MagicMock()
    mock_executor.execute_one_node.return_value = None
    NodeExecutorCls = MagicMock(return_value=mock_executor)
    type(conn.mech_jeb).NodeExecutor = NodeExecutorCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 5}
        )

    NodeExecutorCls.assert_called_once_with(5, conn)
    mock_executor.execute_one_node.assert_called_once()
    assert result[0].text == "OK"


def test_mechjeb_get_api_ready_bypasses_guard():
    """The get_APIReady tool itself is never blocked by the guard."""
    conn = _make_conn(api_ready=False)
    conn.mech_jeb.api_ready = False  # confirm not-ready

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        # Guard is skipped for get_APIReady so no blocking error even when False
        result = bridge.call_tool("mech_jeb_get_api_ready", {})

    assert "APIReady is false" not in result[0].text


# ---------------------------------------------------------------------------
# OperationException error handling
# ---------------------------------------------------------------------------

def test_operation_exception_surfaced_as_mechjeb_error():
    """RPCError containing 'OperationException' is returned as a structured MechJeb error."""
    conn = _make_conn(api_ready=True)

    mock_op = MagicMock()
    OperationCircularizeCls = MagicMock(return_value=mock_op)
    type(conn.mech_jeb).OperationCircularize = OperationCircularizeCls
    mock_op.make_nodes.side_effect = krpc.error.RPCError(
        "OperationException: no orbit to circularize"
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_operation_circularize_make_nodes", {"this": 10}
        )

    assert "MechJeb operation error" in result[0].text
    assert "OperationException" in result[0].text


def test_generic_rpc_error_surfaced_without_mechjeb_prefix():
    """A plain RPCError (no OperationException) returns kRPC RPC error text."""
    conn = _make_conn(api_ready=True)

    mock_executor = MagicMock()
    NodeExecutorCls = MagicMock(return_value=mock_executor)
    type(conn.mech_jeb).NodeExecutor = NodeExecutorCls
    mock_executor.execute_one_node.side_effect = krpc.error.RPCError("connection lost")

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 5}
        )

    assert "kRPC RPC error" in result[0].text
    assert "MechJeb operation error" not in result[0].text


# ---------------------------------------------------------------------------
# Integration scenario: ascent launch
# ---------------------------------------------------------------------------

def test_ascent_launch():
    """
    Ascent launch scenario:
      1. Get AscentAutopilot handle
      2. Set desired orbit altitude (100 km)
      3. Enable autopilot
    """
    conn = _make_conn(api_ready=True)

    mock_ap = MagicMock()
    AscentAutopilotCls = MagicMock(return_value=mock_ap)
    type(conn.mech_jeb).AscentAutopilot = AscentAutopilotCls

    # Simulate get_AscentAutopilot returning an object ID
    conn.mech_jeb.ascent_autopilot._object_id = 99

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()

        # Step 1: get handle
        result = bridge.call_tool("mech_jeb_get_ascent_autopilot", {})
        assert "AscentAutopilot" in result[0].text or "99" in result[0].text

        # Step 2: set desired orbit altitude to 100 km
        result = bridge.call_tool(
            "mech_jeb_ascent_autopilot_set_desired_orbit_altitude",
            {"this": 99, "value": 100000.0},
        )
        AscentAutopilotCls.assert_called_with(99, conn)
        assert mock_ap.desired_orbit_altitude == 100000.0
        assert result[0].text == "OK"

        # Step 3: enable autopilot
        result = bridge.call_tool(
            "mech_jeb_ascent_autopilot_set_enabled", {"this": 99, "value": True}
        )
        assert mock_ap.enabled is True
        assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Integration scenario: circularize node creation + execution
# ---------------------------------------------------------------------------

def test_circularize_node_creation_and_execution():
    """
    Circularize scenario:
      1. Get ManeuverPlanner handle
      2. Get OperationCircularize handle
      3. Call MakeNodes() — returns list of node object IDs
      4. Get NodeExecutor handle
      5. ExecuteOneNode()
    """
    conn = _make_conn(api_ready=True)

    mock_planner = MagicMock()
    ManeuverPlannerCls = MagicMock(return_value=mock_planner)
    type(conn.mech_jeb).ManeuverPlanner = ManeuverPlannerCls

    mock_op = MagicMock()
    mock_op.make_nodes.return_value = []
    OperationCircularizeCls = MagicMock(return_value=mock_op)
    type(conn.mech_jeb).OperationCircularize = OperationCircularizeCls

    mock_executor = MagicMock()
    mock_executor.execute_one_node.return_value = None
    NodeExecutorCls = MagicMock(return_value=mock_executor)
    type(conn.mech_jeb).NodeExecutor = NodeExecutorCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()

        # Step 3: make circularize nodes
        result = bridge.call_tool(
            "mech_jeb_operation_circularize_make_nodes", {"this": 20}
        )
        OperationCircularizeCls.assert_called_once_with(20, conn)
        mock_op.make_nodes.assert_called_once()
        assert result[0].text == "[]"

        # Step 5: execute node
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 30}
        )
        NodeExecutorCls.assert_called_once_with(30, conn)
        mock_executor.execute_one_node.assert_called_once()
        assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Integration scenario: landing
# ---------------------------------------------------------------------------

def test_landing_untargeted():
    """LandingAutopilot.LandUntargeted() dispatches correctly."""
    conn = _make_conn(api_ready=True)

    mock_lander = MagicMock()
    mock_lander.land_untargeted.return_value = None
    LandingAutopilotCls = MagicMock(return_value=mock_lander)
    type(conn.mech_jeb).LandingAutopilot = LandingAutopilotCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_landing_autopilot_land_untargeted", {"this": 40}
        )

    LandingAutopilotCls.assert_called_once_with(40, conn)
    mock_lander.land_untargeted.assert_called_once()
    assert result[0].text == "OK"


def test_landing_set_touchdown_speed():
    """LandingAutopilot touchdown speed setter works via bridge."""
    conn = _make_conn(api_ready=True)

    mock_lander = MagicMock()
    LandingAutopilotCls = MagicMock(return_value=mock_lander)
    type(conn.mech_jeb).LandingAutopilot = LandingAutopilotCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_landing_autopilot_set_touchdown_speed",
            {"this": 40, "value": 2.0},
        )

    assert mock_lander.touchdown_speed == 2.0
    assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Integration scenario: docking approach
# ---------------------------------------------------------------------------

def test_docking_approach_enable():
    """DockingAutopilot.Enabled = True dispatches as a property setter."""
    conn = _make_conn(api_ready=True)

    mock_docker = MagicMock()
    DockingAutopilotCls = MagicMock(return_value=mock_docker)
    type(conn.mech_jeb).DockingAutopilot = DockingAutopilotCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_docking_autopilot_set_enabled", {"this": 50, "value": True}
        )

    DockingAutopilotCls.assert_called_once_with(50, conn)
    assert mock_docker.enabled is True
    assert result[0].text == "OK"


def test_docking_approach_set_speed_limit():
    """DockingAutopilot speed limit setter dispatches correctly."""
    conn = _make_conn(api_ready=True)

    mock_docker = MagicMock()
    DockingAutopilotCls = MagicMock(return_value=mock_docker)
    type(conn.mech_jeb).DockingAutopilot = DockingAutopilotCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_docking_autopilot_set_speed_limit", {"this": 50, "value": 1.5}
        )

    assert mock_docker.speed_limit == 1.5
    assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Node executor controls
# ---------------------------------------------------------------------------

def test_node_executor_autowarp_and_abort():
    """NodeExecutor autowarp setter and abort method dispatch correctly."""
    conn = _make_conn(api_ready=True)

    mock_executor = MagicMock()
    mock_executor.abort.return_value = None
    NodeExecutorCls = MagicMock(return_value=mock_executor)
    type(conn.mech_jeb).NodeExecutor = NodeExecutorCls

    with patch("krpc_mcp.bridge.get_connection", return_value=conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()

        result = bridge.call_tool(
            "mech_jeb_node_executor_set_autowarp", {"this": 60, "value": True}
        )
        assert mock_executor.autowarp is True
        assert result[0].text == "OK"

        result = bridge.call_tool("mech_jeb_node_executor_abort", {"this": 60})
        mock_executor.abort.assert_called_once()
        assert result[0].text == "OK"
