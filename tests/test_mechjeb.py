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

from ._helpers import build_proxy

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
        # NOTE: MechJeb 2.15.2 does NOT expose Operation.getErrorMessage(); only
        # MakeNode/MakeNodes are present. Node creation must remain decoupled
        # from the (absent) error-readback accessor — see the regression test
        # `test_node_creation_independent_of_error_message_accessor` below.
        _make_proc("OperationCircularize_MakeNodes",
                   params=[_this("OperationCircularize")], return_code=TC_LIST),

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


def test_mechjeb_api_ready_allows_tool_call(mechjeb_env):
    """When APIReady is True, the tool call proceeds normally."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    invocations: list = []
    instances: list = []

    def execute_one_node(self, **kwargs):
        invocations.append(kwargs)
        return None

    mechjeb_env.module.NodeExecutor = build_proxy(
        "NodeExecutor",
        methods={"execute_one_node": execute_one_node},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 5}
        )

    assert (instances[0]._client, instances[0]._object_id) == (mechjeb_env.conn, 5)
    assert invocations == [{}]
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

def test_operation_exception_surfaced_as_mechjeb_error(mechjeb_env):
    """RPCError containing 'OperationException' is returned as a structured MechJeb error."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    def make_nodes(self, **kwargs):
        raise krpc.error.RPCError("OperationException: no orbit to circularize")

    mechjeb_env.module.OperationCircularize = build_proxy(
        "OperationCircularize", methods={"make_nodes": make_nodes}
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_operation_circularize_make_nodes", {"this": 10}
        )

    assert "MechJeb operation error" in result[0].text
    assert "OperationException" in result[0].text


def test_generic_rpc_error_surfaced_without_mechjeb_prefix(mechjeb_env):
    """A plain RPCError (no OperationException) returns kRPC RPC error text."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    def execute_one_node(self, **kwargs):
        raise krpc.error.RPCError("connection lost")

    mechjeb_env.module.NodeExecutor = build_proxy(
        "NodeExecutor", methods={"execute_one_node": execute_one_node}
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
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

def test_ascent_launch(mechjeb_env):
    """
    Ascent launch scenario:
      1. Get AscentAutopilot handle
      2. Set desired orbit altitude (100 km)
      3. Enable autopilot
    """
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    # Step 1's get_AscentAutopilot reads the service-level property; provide an
    # object with the canonical _object_id so format_result returns "id=99".
    mock_ap_handle = MagicMock()
    mock_ap_handle._object_id = 99
    mechjeb_env.conn.mech_jeb.ascent_autopilot = mock_ap_handle

    instances: list = []
    mechjeb_env.module.AscentAutopilot = build_proxy(
        "AscentAutopilot",
        properties={"desired_orbit_altitude": None, "enabled": False},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
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
        assert (instances[-1]._client, instances[-1]._object_id) == (
            mechjeb_env.conn,
            99,
        )
        assert instances[-1].desired_orbit_altitude == 100000.0
        assert result[0].text == "OK"

        # Step 3: enable autopilot
        result = bridge.call_tool(
            "mech_jeb_ascent_autopilot_set_enabled", {"this": 99, "value": True}
        )
        assert instances[-1].enabled is True
        assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Integration scenario: circularize node creation + execution
# ---------------------------------------------------------------------------

def test_circularize_node_creation_and_execution(mechjeb_env):
    """
    Circularize scenario:
      1. Get ManeuverPlanner handle (not exercised here — covered by discovery)
      2. Get OperationCircularize handle
      3. Call MakeNodes() — returns list of node object IDs
      4. Get NodeExecutor handle
      5. ExecuteOneNode()
    """
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    op_calls: list = []
    op_instances: list = []
    exec_calls: list = []
    exec_instances: list = []

    def make_nodes(self, **kwargs):
        op_calls.append(kwargs)
        return []

    def execute_one_node(self, **kwargs):
        exec_calls.append(kwargs)
        return None

    mechjeb_env.module.OperationCircularize = build_proxy(
        "OperationCircularize",
        methods={"make_nodes": make_nodes},
        instances=op_instances,
    )
    mechjeb_env.module.NodeExecutor = build_proxy(
        "NodeExecutor",
        methods={"execute_one_node": execute_one_node},
        instances=exec_instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()

        # Step 3: make circularize nodes
        result = bridge.call_tool(
            "mech_jeb_operation_circularize_make_nodes", {"this": 20}
        )
        assert (op_instances[0]._client, op_instances[0]._object_id) == (
            mechjeb_env.conn,
            20,
        )
        assert op_calls == [{}]
        assert result[0].text == "[]"

        # Step 5: execute node
        result = bridge.call_tool(
            "mech_jeb_node_executor_execute_one_node", {"this": 30}
        )
        assert (exec_instances[0]._client, exec_instances[0]._object_id) == (
            mechjeb_env.conn,
            30,
        )
        assert exec_calls == [{}]
        assert result[0].text == "OK"


def test_node_creation_independent_of_error_message_accessor(mechjeb_env):
    """Regression: maneuver-node creation must not depend on Operation.getErrorMessage().

    MechJeb 2.15.2 does not expose ``Operation.getErrorMessage()``; only
    ``MakeNode`` / ``MakeNodes`` are present on the Operation* classes. This
    test pins two invariants so a future "let me enrich errors by calling
    get_ErrorMessage" refactor can't silently couple them:

      1. Discovery registers ``*_make_nodes`` even when no
         ``*_get_error_message`` procedure exists in the schema.
      2. The OperationException wrapper in ``bridge.call_tool`` produces the
         structured "MechJeb operation error" message using only the RPC
         exception text — it never reads ``error_message`` off the proxy.
    """
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    error_message_reads: list = []

    class _CircularizeProxy:
        def __init__(self, client, object_id):
            self._client = client
            self._object_id = object_id

        def make_nodes(self, **kwargs):
            raise krpc.error.RPCError(
                "OperationException: no orbit to circularize"
            )

        @property
        def error_message(self):
            error_message_reads.append("read")
            raise AssertionError(
                "bridge must not read Operation.error_message during error wrapping"
            )

    mechjeb_env.module.OperationCircularize = _CircularizeProxy

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        names = {t.name for t in bridge.list_tools()}

        # Invariant 1: node-creation tool registered, error-readback tool absent.
        assert "mech_jeb_operation_circularize_make_nodes" in names
        assert "mech_jeb_operation_apoapsis_make_nodes" in names
        assert not any(n.endswith("_get_error_message") for n in names), (
            "MechJeb 2.15.2 schema must not expose *_get_error_message tools"
        )

        # Invariant 2: OperationException wrapping uses RPC exception text only.
        result = bridge.call_tool(
            "mech_jeb_operation_circularize_make_nodes", {"this": 20}
        )

    assert "MechJeb operation error" in result[0].text
    assert "no orbit to circularize" in result[0].text
    assert error_message_reads == []


# ---------------------------------------------------------------------------
# Integration scenario: landing
# ---------------------------------------------------------------------------

def test_landing_untargeted(mechjeb_env):
    """LandingAutopilot.LandUntargeted() dispatches correctly."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    instances: list = []
    calls: list = []

    def land_untargeted(self, **kwargs):
        calls.append(kwargs)
        return None

    mechjeb_env.module.LandingAutopilot = build_proxy(
        "LandingAutopilot",
        methods={"land_untargeted": land_untargeted},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_landing_autopilot_land_untargeted", {"this": 40}
        )

    assert (instances[0]._client, instances[0]._object_id) == (mechjeb_env.conn, 40)
    assert calls == [{}]
    assert result[0].text == "OK"


def test_landing_set_touchdown_speed(mechjeb_env):
    """LandingAutopilot touchdown speed setter works via bridge."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    instances: list = []
    mechjeb_env.module.LandingAutopilot = build_proxy(
        "LandingAutopilot",
        properties={"touchdown_speed": None},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_landing_autopilot_set_touchdown_speed",
            {"this": 40, "value": 2.0},
        )

    assert instances[0].touchdown_speed == 2.0
    assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Integration scenario: docking approach
# ---------------------------------------------------------------------------

def test_docking_approach_enable(mechjeb_env):
    """DockingAutopilot.Enabled = True dispatches as a property setter."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    instances: list = []
    mechjeb_env.module.DockingAutopilot = build_proxy(
        "DockingAutopilot",
        properties={"enabled": False},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_docking_autopilot_set_enabled", {"this": 50, "value": True}
        )

    assert (instances[0]._client, instances[0]._object_id) == (mechjeb_env.conn, 50)
    assert instances[0].enabled is True
    assert result[0].text == "OK"


def test_docking_approach_set_speed_limit(mechjeb_env):
    """DockingAutopilot speed limit setter dispatches correctly."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    instances: list = []
    mechjeb_env.module.DockingAutopilot = build_proxy(
        "DockingAutopilot",
        properties={"speed_limit": None},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        result = bridge.call_tool(
            "mech_jeb_docking_autopilot_set_speed_limit", {"this": 50, "value": 1.5}
        )

    assert instances[0].speed_limit == 1.5
    assert result[0].text == "OK"


# ---------------------------------------------------------------------------
# Node executor controls
# ---------------------------------------------------------------------------

def test_node_executor_autowarp_and_abort(mechjeb_env):
    """NodeExecutor autowarp setter and abort method dispatch correctly."""
    mechjeb_env.conn.krpc.get_services.return_value = _make_mechjeb_services()
    mechjeb_env.conn.mech_jeb.api_ready = True

    instances: list = []
    abort_calls: list = []

    def abort(self, **kwargs):
        abort_calls.append(kwargs)
        return None

    mechjeb_env.module.NodeExecutor = build_proxy(
        "NodeExecutor",
        properties={"autowarp": False},
        methods={"abort": abort},
        instances=instances,
    )

    with patch("krpc_mcp.bridge.get_connection", return_value=mechjeb_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()

        result = bridge.call_tool(
            "mech_jeb_node_executor_set_autowarp", {"this": 60, "value": True}
        )
        assert instances[-1].autowarp is True
        assert result[0].text == "OK"

        result = bridge.call_tool("mech_jeb_node_executor_abort", {"this": 60})
        assert abort_calls == [{}]
        assert result[0].text == "OK"
