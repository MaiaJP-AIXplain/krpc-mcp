"""Vessel control endpoint coverage: discovery, schema, and invocation tests.

Covers the full set of SpaceCenter procedures needed to control a vessel:
  Vessel, Control, AutoPilot, Flight, and Orbit.
"""

from unittest.mock import MagicMock, patch

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
TC_ENUMERATION = 101
TC_LIST = 301


# ---------------------------------------------------------------------------
# Mock-building helpers
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


def _this(class_name):
    """Required 'this' parameter of type TC_CLASS."""
    return _make_param("this", TC_CLASS, "SpaceCenter", class_name)


def _make_proc(pname, params=None, return_code=TC_NONE, return_service="", return_name="", doc=""):
    proc = MagicMock()
    proc.name = pname
    proc.parameters = params or []
    proc.return_type = _make_type(return_code, return_service, return_name)
    proc.documentation = doc
    return proc


def _class_ret(class_name):
    return dict(return_code=TC_CLASS, return_service="SpaceCenter", return_name=class_name)


def _make_vessel_control_services():
    """Full mock SpaceCenter schema covering all vessel-control procedures."""
    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        # --- Vessel ---
        _make_proc("get_ActiveVessel", **_class_ret("Vessel")),
        _make_proc("get_Vessels", return_code=TC_LIST),
        _make_proc("Vessel_get_Name",
                   params=[_this("Vessel")], return_code=TC_STRING),
        _make_proc("Vessel_get_MET",
                   params=[_this("Vessel")], return_code=TC_DOUBLE),
        _make_proc("Vessel_get_Mass",
                   params=[_this("Vessel")], return_code=TC_FLOAT),
        _make_proc("Vessel_get_Situation",
                   params=[_this("Vessel")], return_code=TC_ENUMERATION),
        _make_proc("Vessel_get_SurfaceReferenceFrame",
                   params=[_this("Vessel")], **_class_ret("ReferenceFrame")),

        # --- Control ---
        _make_proc("Vessel_get_Control",
                   params=[_this("Vessel")], **_class_ret("Control")),
        _make_proc("Control_get_Throttle",
                   params=[_this("Control")], return_code=TC_FLOAT),
        _make_proc("Control_set_Throttle",
                   params=[_this("Control"), _make_param("value", TC_FLOAT)]),
        _make_proc("Control_get_SAS",
                   params=[_this("Control")], return_code=TC_BOOL),
        _make_proc("Control_set_SAS",
                   params=[_this("Control"), _make_param("value", TC_BOOL)]),
        _make_proc("Control_get_SASMode",
                   params=[_this("Control")], return_code=TC_ENUMERATION),
        _make_proc("Control_set_SASMode",
                   params=[_this("Control"), _make_param("value", TC_ENUMERATION)]),
        _make_proc("Control_get_RCS",
                   params=[_this("Control")], return_code=TC_BOOL),
        _make_proc("Control_set_RCS",
                   params=[_this("Control"), _make_param("value", TC_BOOL)]),
        _make_proc("Control_get_Gear",
                   params=[_this("Control")], return_code=TC_BOOL),
        _make_proc("Control_set_Gear",
                   params=[_this("Control"), _make_param("value", TC_BOOL)]),
        _make_proc("Control_ActivateNextStage",
                   params=[_this("Control")], return_code=TC_LIST),

        # --- AutoPilot ---
        _make_proc("Vessel_get_AutoPilot",
                   params=[_this("Vessel")], **_class_ret("AutoPilot")),
        _make_proc("AutoPilot_Engage",
                   params=[_this("AutoPilot")]),
        _make_proc("AutoPilot_Disengage",
                   params=[_this("AutoPilot")]),
        _make_proc("AutoPilot_get_TargetPitch",
                   params=[_this("AutoPilot")], return_code=TC_FLOAT),
        _make_proc("AutoPilot_set_TargetPitch",
                   params=[_this("AutoPilot"), _make_param("value", TC_FLOAT)]),
        _make_proc("AutoPilot_set_TargetHeading",
                   params=[_this("AutoPilot"), _make_param("value", TC_FLOAT)]),
        _make_proc("AutoPilot_set_TargetRoll",
                   params=[_this("AutoPilot"), _make_param("value", TC_FLOAT)]),
        _make_proc("AutoPilot_get_Error",
                   params=[_this("AutoPilot")], return_code=TC_FLOAT),

        # --- Flight ---
        _make_proc("Vessel_get_Flight",
                   params=[_this("Vessel")], **_class_ret("Flight")),
        _make_proc("Flight_get_Altitude",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_MeanAltitude",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_SurfaceAltitude",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_Latitude",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_Longitude",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_Speed",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_VerticalSpeed",
                   params=[_this("Flight")], return_code=TC_DOUBLE),
        _make_proc("Flight_get_Heading",
                   params=[_this("Flight")], return_code=TC_FLOAT),
        _make_proc("Flight_get_Pitch",
                   params=[_this("Flight")], return_code=TC_FLOAT),
        _make_proc("Flight_get_Roll",
                   params=[_this("Flight")], return_code=TC_FLOAT),
        _make_proc("Flight_get_GForce",
                   params=[_this("Flight")], return_code=TC_FLOAT),

        # --- Orbit ---
        _make_proc("Vessel_get_Orbit",
                   params=[_this("Vessel")], **_class_ret("Orbit")),
        _make_proc("Orbit_get_ApoapsisAltitude",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_PeriapsisAltitude",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_Eccentricity",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_Inclination",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_Period",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_TimeToApoapsis",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_TimeToPeriapsis",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_SemiMajorAxis",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
        _make_proc("Orbit_get_OrbitalSpeed",
                   params=[_this("Orbit")], return_code=TC_DOUBLE),
    ]

    services = MagicMock()
    services.services = [sc]
    return services


def _make_bridge():
    """Construct a KrpcBridge with the full vessel-control mock schema."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        tools = {t.name: t for t in bridge.list_tools()}
    return bridge, mock_conn, tools


# ---------------------------------------------------------------------------
# Expected tool name sets (derived from kRPC → snake_case mapping)
# ---------------------------------------------------------------------------

EXPECTED_VESSEL_TOOLS = {
    "space_center_get_active_vessel",
    "space_center_vessel_get_name",
    "space_center_vessel_get_met",
    "space_center_vessel_get_mass",
    "space_center_vessel_get_situation",
    "space_center_vessel_get_surface_reference_frame",
}

EXPECTED_CONTROL_TOOLS = {
    "space_center_vessel_get_control",
    "space_center_control_get_throttle",
    "space_center_control_set_throttle",
    "space_center_control_get_sas",
    "space_center_control_set_sas",
    "space_center_control_get_sas_mode",
    "space_center_control_set_sas_mode",
    "space_center_control_get_rcs",
    "space_center_control_set_rcs",
    "space_center_control_get_gear",
    "space_center_control_set_gear",
    "space_center_control_activate_next_stage",
}

EXPECTED_AUTOPILOT_TOOLS = {
    "space_center_vessel_get_auto_pilot",
    "space_center_auto_pilot_engage",
    "space_center_auto_pilot_disengage",
    "space_center_auto_pilot_get_target_pitch",
    "space_center_auto_pilot_set_target_pitch",
    "space_center_auto_pilot_set_target_heading",
    "space_center_auto_pilot_set_target_roll",
    "space_center_auto_pilot_get_error",
}

EXPECTED_FLIGHT_TOOLS = {
    "space_center_vessel_get_flight",
    "space_center_flight_get_altitude",
    "space_center_flight_get_mean_altitude",
    "space_center_flight_get_surface_altitude",
    "space_center_flight_get_latitude",
    "space_center_flight_get_longitude",
    "space_center_flight_get_speed",
    "space_center_flight_get_vertical_speed",
    "space_center_flight_get_heading",
    "space_center_flight_get_pitch",
    "space_center_flight_get_roll",
    "space_center_flight_get_g_force",
}

EXPECTED_ORBIT_TOOLS = {
    "space_center_vessel_get_orbit",
    "space_center_orbit_get_apoapsis_altitude",
    "space_center_orbit_get_periapsis_altitude",
    "space_center_orbit_get_eccentricity",
    "space_center_orbit_get_inclination",
    "space_center_orbit_get_period",
    "space_center_orbit_get_time_to_apoapsis",
    "space_center_orbit_get_time_to_periapsis",
    "space_center_orbit_get_semi_major_axis",
    "space_center_orbit_get_orbital_speed",
}


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------

def test_vessel_tools_discovered():
    """All core Vessel procedures are registered as MCP tools."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}
    assert EXPECTED_VESSEL_TOOLS <= names


def test_control_tools_discovered():
    """All Control procedures (throttle, SAS, RCS, gear, staging) are registered."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}
    assert EXPECTED_CONTROL_TOOLS <= names


def test_autopilot_tools_discovered():
    """All AutoPilot procedures are registered."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}
    assert EXPECTED_AUTOPILOT_TOOLS <= names


def test_flight_tools_discovered():
    """All Flight telemetry procedures are registered."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}
    assert EXPECTED_FLIGHT_TOOLS <= names


def test_orbit_tools_discovered():
    """All Orbit telemetry procedures are registered."""
    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = _make_vessel_control_services()
    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        names = {t.name for t in KrpcBridge().list_tools()}
    assert EXPECTED_ORBIT_TOOLS <= names


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_control_set_throttle_schema():
    """Throttle setter has 'this' (integer) and 'value' (number), both required."""
    _, _, tools = _make_bridge()
    schema = tools["space_center_control_set_throttle"].inputSchema
    assert schema["properties"]["this"]["type"] == "integer"
    assert schema["properties"]["value"]["type"] == "number"
    assert "this" in schema["required"]
    assert "value" in schema["required"]


def test_control_set_sas_mode_schema():
    """SASMode setter maps the enum parameter to an integer."""
    _, _, tools = _make_bridge()
    schema = tools["space_center_control_set_sas_mode"].inputSchema
    assert schema["properties"]["value"]["type"] == "integer"
    assert "value" in schema["required"]


def test_control_set_sas_schema():
    """SAS enable/disable setter maps the bool parameter correctly."""
    _, _, tools = _make_bridge()
    schema = tools["space_center_control_set_sas"].inputSchema
    assert schema["properties"]["value"]["type"] == "boolean"


def test_flight_get_altitude_schema():
    """Flight altitude getter only requires 'this'."""
    _, _, tools = _make_bridge()
    schema = tools["space_center_flight_get_altitude"].inputSchema
    assert schema["properties"]["this"]["type"] == "integer"
    assert schema["required"] == ["this"]


# ---------------------------------------------------------------------------
# Invocation tests — driven through the kspc_env fixture so they exercise the
# real (module-level class lookup, (client, object_id) constructor) contract.
# ---------------------------------------------------------------------------


def test_invoke_get_active_vessel(kspc_env):
    """get_ActiveVessel returns the vessel's remote object ID."""
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()
    mock_vessel = MagicMock()
    mock_vessel._object_id = 101
    # Service-level getter hits the service proxy; no class proxy involved.
    kspc_env.conn.space_center.active_vessel = mock_vessel

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("space_center_get_active_vessel", {})

    assert "101" in result[0].text


def test_invoke_control_set_throttle(kspc_env):
    """Throttle setter calls setattr with the float value."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"throttle": None}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_control_set_throttle", {"this": 5, "value": 0.8}
        )

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 5)
    assert instances[0].throttle == 0.8
    assert result[0].text == "OK"


def test_invoke_control_set_sas(kspc_env):
    """SAS setter calls setattr with the bool value."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"sas": False}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_control_set_sas", {"this": 5, "value": True}
        )

    assert instances[0].sas is True
    assert result[0].text == "OK"


def test_invoke_control_set_sas_mode(kspc_env):
    """SAS mode setter passes the integer enum value to the proxy."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"sas_mode": None}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        # SASMode.stability_assist = 0
        result = KrpcBridge().call_tool(
            "space_center_control_set_sas_mode", {"this": 5, "value": 0}
        )

    assert instances[0].sas_mode == 0
    assert result[0].text == "OK"


def test_invoke_control_set_rcs(kspc_env):
    """RCS setter calls setattr with a bool."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"rcs": False}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_control_set_rcs", {"this": 5, "value": True}
        )

    assert instances[0].rcs is True
    assert result[0].text == "OK"


def test_invoke_control_set_gear(kspc_env):
    """Gear setter calls setattr with a bool."""
    instances: list = []
    kspc_env.module.Control = build_proxy(
        "Control", properties={"gear": False}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_control_set_gear", {"this": 5, "value": True}
        )

    assert instances[0].gear is True
    assert result[0].text == "OK"


def test_invoke_control_activate_next_stage(kspc_env):
    """ActivateNextStage returns a JSON list of activated part object IDs."""
    part1, part2 = MagicMock(), MagicMock()
    part1._object_id = 201
    part2._object_id = 202
    invocations: list = []

    def activate_next_stage(self, **kwargs):
        invocations.append(kwargs)
        return [part1, part2]

    kspc_env.module.Control = build_proxy(
        "Control", methods={"activate_next_stage": activate_next_stage}
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_control_activate_next_stage", {"this": 5}
        )

    assert invocations == [{}]
    assert "201" in result[0].text
    assert "202" in result[0].text


def test_invoke_autopilot_engage(kspc_env):
    """AutoPilot.Engage calls engage() on the proxy."""
    calls: list = []

    def engage(self, **kwargs):
        calls.append(kwargs)
        return None

    kspc_env.module.AutoPilot = build_proxy("AutoPilot", methods={"engage": engage})
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("space_center_auto_pilot_engage", {"this": 3})

    assert calls == [{}]
    assert result[0].text == "OK"


def test_invoke_autopilot_disengage(kspc_env):
    """AutoPilot.Disengage calls disengage() on the proxy."""
    calls: list = []

    def disengage(self, **kwargs):
        calls.append(kwargs)
        return None

    kspc_env.module.AutoPilot = build_proxy("AutoPilot", methods={"disengage": disengage})
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("space_center_auto_pilot_disengage", {"this": 3})

    assert calls == [{}]
    assert result[0].text == "OK"


def test_invoke_autopilot_set_target_pitch(kspc_env):
    """AutoPilot target pitch setter uses setattr."""
    instances: list = []
    kspc_env.module.AutoPilot = build_proxy(
        "AutoPilot", properties={"target_pitch": None}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_auto_pilot_set_target_pitch", {"this": 3, "value": 45.0}
        )

    assert instances[0].target_pitch == 45.0
    assert result[0].text == "OK"


def test_invoke_flight_get_altitude(kspc_env):
    """Flight altitude getter reads the altitude property from the proxy."""
    instances: list = []
    kspc_env.module.Flight = build_proxy(
        "Flight", properties={"altitude": 10000.0}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("space_center_flight_get_altitude", {"this": 9})

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 9)
    assert "10000.0" in result[0].text


def test_invoke_flight_get_speed(kspc_env):
    """Flight speed getter reads the speed property from the proxy."""
    kspc_env.module.Flight = build_proxy("Flight", properties={"speed": 2200.5})
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool("space_center_flight_get_speed", {"this": 9})

    assert "2200.5" in result[0].text


def test_invoke_orbit_get_apoapsis_altitude(kspc_env):
    """Orbit apoapsis altitude getter reads the property from the proxy."""
    instances: list = []
    kspc_env.module.Orbit = build_proxy(
        "Orbit", properties={"apoapsis_altitude": 75000.0}, instances=instances
    )
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_orbit_get_apoapsis_altitude", {"this": 11}
        )

    assert (instances[0]._client, instances[0]._object_id) == (kspc_env.conn, 11)
    assert "75000.0" in result[0].text


def test_invoke_orbit_get_inclination(kspc_env):
    """Orbit inclination getter reads the property from the proxy."""
    kspc_env.module.Orbit = build_proxy("Orbit", properties={"inclination": 28.5})
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_control_services()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        from krpc_mcp.bridge import KrpcBridge
        result = KrpcBridge().call_tool(
            "space_center_orbit_get_inclination", {"this": 11}
        )

    assert "28.5" in result[0].text
