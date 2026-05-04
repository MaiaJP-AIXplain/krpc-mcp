"""Pins the kRPC class-proxy integration contract.

Two assumptions are load-bearing for every class-member tool the bridge
exposes:

  1. Generated proxy classes (``Vessel``, ``Control``, ``Flight``, ...) live as
     ``module-level`` members of the kRPC service module — *not* as nested
     classes on the service type.
  2. Their constructor signature is ``__init__(client, object_id)``.

Both have been broken in the past in ways that ``MagicMock``-only tests could
not catch (the wrong attribute was mocked, or the wrong call shape was
asserted, and discovery never raised). The tests below reproduce the exact
real-world contract end-to-end through ``KrpcBridge.call_tool``.

If a future contributor reverts to ``cls(instance_id, conn)`` or starts
searching ``type(svc)`` again, *these* tests fail — preventing a regression
of the silent-no-tools / vessel-not-found classes of bug.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from krpc_mcp.bridge import KrpcBridge

# Mirrors the protobuf TypeCode values (kept inline to avoid coupling tests to
# private schema constants).
TC_DOUBLE = 1
TC_BOOL = 7
TC_STRING = 8
TC_CLASS = 100
TC_NONE = 0


def _proto_type(code, service="", name="", types=None):
    t = MagicMock()
    t.code = code
    t.service = service
    t.name = name
    t.types = types or []
    return t


def _proto_param(pname, type_code, *, service="", type_name="", default_value=b""):
    p = MagicMock()
    p.name = pname
    p.type = _proto_type(type_code, service, type_name)
    p.default_value = default_value
    p.documentation = ""
    return p


def _proto_proc(pname, *, params=None, return_code=TC_NONE, return_service="", return_name=""):
    proc = MagicMock()
    proc.name = pname
    proc.parameters = params or []
    proc.return_type = _proto_type(return_code, return_service, return_name)
    proc.documentation = ""
    return proc


def _make_vessel_get_name_schema():
    """Minimal schema with a single class-member procedure: Vessel.get_Name."""
    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        _proto_proc(
            "Vessel_get_Name",
            params=[_proto_param("this", TC_CLASS, service="SpaceCenter", type_name="Vessel")],
            return_code=TC_STRING,
        ),
    ]

    services = MagicMock()
    services.services = [sc]
    return services


def test_proxy_class_is_resolved_from_service_module(kspc_env):
    """Bridge looks up proxy classes in ``sys.modules[type(svc).__module__]``.

    Regression: prior implementation searched ``type(conn.space_center)`` for
    a nested ``Vessel`` attribute, which kRPC never exposes there.
    """
    constructed: list[tuple] = []

    class FakeVessel:
        def __init__(self, client, object_id):
            constructed.append((client, object_id))
            self._client = client
            self._object_id = object_id
            self.name = f"vessel-{object_id}"

    kspc_env.module.Vessel = FakeVessel
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_get_name_schema()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool("space_center_vessel_get_name", {"this": 7})

    assert constructed == [(kspc_env.conn, 7)], (
        "Proxy must be constructed as cls(client, object_id); regression to "
        "cls(object_id, client) silently breaks every class-member tool."
    )
    assert result[0].text == "vessel-7"


def test_proxy_class_not_present_returns_clear_error(kspc_env):
    """Missing proxy class → MCP-friendly error naming the missing class and module."""
    # Intentionally do *not* register Vessel on the module.
    kspc_env.conn.krpc.get_services.return_value = _make_vessel_get_name_schema()

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool("space_center_vessel_get_name", {"this": 1})

    text = result[0].text
    assert "Vessel" in text
    assert kspc_env.module.__name__ in text
    # The hint helps users who incorrectly threaded a vessel handle into Control_*.
    assert "handle" in text.lower()


def test_proxy_class_qualified_name_resolves_to_leaf(kspc_env):
    """Schemas reporting "SpaceCenter.Vessel" still resolve to the bare class.

    Some kRPC builds emit fully qualified class names. The bridge must split on
    "." and prefer the leaf segment because that's what the code generator
    actually exports as a module attribute.
    """
    constructed: list[tuple] = []

    class FakeVessel:
        def __init__(self, client, object_id):
            constructed.append((client, object_id))
            self._client = client
            self._object_id = object_id
            self.name = f"qual-{object_id}"

    kspc_env.module.Vessel = FakeVessel
    services = _make_vessel_get_name_schema()
    services.services[0].procedures[0].parameters[0].type.name = "SpaceCenter.Vessel"
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool("space_center_vessel_get_name", {"this": 3})

    assert constructed == [(kspc_env.conn, 3)]
    assert result[0].text == "qual-3"


def test_setter_dispatches_through_python_property(kspc_env):
    """Bridge ``set_*`` dispatch must go through the Python property setter.

    kRPC exposes ``Control_set_Throttle`` as ``Control.throttle = value`` — a
    real ``@property.setter``. The bridge translates ``set_X`` to a ``setattr``
    on the proxy. Pin that contract so a future refactor that calls a
    ``set_throttle`` method instead of the property silently stops working.
    """
    side_effects: list[float] = []

    class FakeControl:
        def __init__(self, client, object_id):
            self._client = client
            self._object_id = object_id

        @property
        def throttle(self) -> float:
            return self._throttle

        @throttle.setter
        def throttle(self, value: float) -> None:
            side_effects.append(value)
            self._throttle = value

    kspc_env.module.Control = FakeControl

    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        _proto_proc(
            "Control_set_Throttle",
            params=[
                _proto_param("this", TC_CLASS, service="SpaceCenter", type_name="Control"),
                _proto_param("value", TC_DOUBLE),
            ],
        ),
    ]
    services = MagicMock()
    services.services = [sc]
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool(
            "space_center_control_set_throttle", {"this": 5, "value": 0.42}
        )

    assert side_effects == [0.42], "setter must reach the @property.setter"
    assert result[0].text == "OK"


def test_method_dispatch_uses_keyword_arguments(kspc_env):
    """Non-get/set methods are called with ``**kwargs`` keyed on schema names.

    kRPC's generated method signatures match the schema parameter names
    exactly, so the bridge passes by keyword. A regression to positional args
    would break any method whose schema order or default values shift.
    """
    captured_kwargs: list[dict] = []

    class FakeAutoPilot:
        def __init__(self, client, object_id):
            self._client = client
            self._object_id = object_id

        def target_pitch_and_heading(self, **kwargs):
            captured_kwargs.append(kwargs)
            return None

    kspc_env.module.AutoPilot = FakeAutoPilot

    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        _proto_proc(
            "AutoPilot_TargetPitchAndHeading",
            params=[
                _proto_param("this", TC_CLASS, service="SpaceCenter", type_name="AutoPilot"),
                _proto_param("pitch", TC_DOUBLE),
                _proto_param("heading", TC_DOUBLE),
            ],
        ),
    ]
    services = MagicMock()
    services.services = [sc]
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool(
            "space_center_auto_pilot_target_pitch_and_heading",
            {"this": 12, "pitch": 45.0, "heading": 90.0},
        )

    assert captured_kwargs == [{"pitch": 45.0, "heading": 90.0}]
    assert result[0].text == "OK"


def test_returned_proxy_is_serialised_with_object_id(kspc_env):
    """Returning a proxy from a getter surfaces the remote handle for chaining.

    A vessel_get_control call must return a value the caller can feed back as
    ``this`` to subsequent Control_* tools. The bridge encodes that as
    ``"<ClassName>(id=<n>)"`` via ``format_result``.
    """

    class FakeControl:
        def __init__(self, client, object_id):
            self._client = client
            self._object_id = object_id

    class FakeVessel:
        def __init__(self, client, object_id):
            self._client = client
            self._object_id = object_id

        @property
        def control(self):
            return FakeControl(self._client, 99)

    kspc_env.module.Vessel = FakeVessel
    kspc_env.module.Control = FakeControl

    sc = MagicMock()
    sc.name = "SpaceCenter"
    sc.procedures = [
        _proto_proc(
            "Vessel_get_Control",
            params=[_proto_param("this", TC_CLASS, service="SpaceCenter", type_name="Vessel")],
            return_code=TC_CLASS,
            return_service="SpaceCenter",
            return_name="Control",
        ),
    ]
    services = MagicMock()
    services.services = [sc]
    kspc_env.conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=kspc_env.conn):
        result = KrpcBridge().call_tool("space_center_vessel_get_control", {"this": 1})

    assert result[0].text == "FakeControl(id=99)"
