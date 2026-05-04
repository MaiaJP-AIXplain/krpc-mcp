"""Regression tests that exercise the real kRPC protobuf descriptors.

The mocks in test_server_builds.py and test_vessel_control.py use MagicMock for
parameters and explicitly set `.documentation = ""`. That masked a bug where
`params_to_input_schema` accessed `param.documentation` even though the kRPC
`Parameter` message has no such field — it only exists on `Procedure`. Against
real protobuf objects the access raised `AttributeError` and aborted discovery,
so `tools/list` returned no tools at all in production.

These tests use real `KRPC_pb2.Parameter` / `KRPC_pb2.Procedure` instances so any
future regression of this kind fails CI.
"""

from unittest.mock import MagicMock, patch

from krpc.schema import KRPC_pb2


def test_parameter_protobuf_has_no_documentation_field():
    """Pin the protobuf schema: Parameter has no `documentation`, Procedure does."""
    param_fields = {f.name for f in KRPC_pb2.Parameter.DESCRIPTOR.fields}
    proc_fields = {f.name for f in KRPC_pb2.Procedure.DESCRIPTOR.fields}
    assert "documentation" not in param_fields
    assert "documentation" in proc_fields


def test_params_to_input_schema_with_real_parameter():
    """Real Parameter objects must not raise — the bug was AttributeError here."""
    from krpc_mcp.type_mapper import params_to_input_schema

    param = KRPC_pb2.Parameter()
    param.name = "ut"
    param.type.code = 1  # TC_DOUBLE
    # default_value left as empty bytes → required

    schema = params_to_input_schema([param])

    assert schema["type"] == "object"
    assert schema["properties"]["ut"] == {"type": "number"}
    assert schema["required"] == ["ut"]


def test_bridge_discovery_with_real_parameter_protobuf():
    """End-to-end: bridge discovery must succeed when params are real protobuf objects.

    Pre-fix, this raised `AttributeError: documentation` and `_tools` ended up empty.
    """
    real_param = KRPC_pb2.Parameter()
    real_param.name = "ut"
    real_param.type.code = 1  # TC_DOUBLE

    proc = MagicMock()
    proc.name = "WarpTo"
    proc.parameters = [real_param]
    proc.return_type = MagicMock(code=0, service="", name="", types=[])
    proc.documentation = ""

    service = MagicMock()
    service.name = "SpaceCenter"
    service.procedures = [proc]

    services = MagicMock()
    services.services = [service]

    mock_conn = MagicMock()
    mock_conn.krpc.get_services.return_value = services

    with patch("krpc_mcp.bridge.get_connection", return_value=mock_conn):
        from krpc_mcp.bridge import KrpcBridge
        bridge = KrpcBridge()
        tools = bridge.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "space_center_warp_to"
    assert tools[0].inputSchema["properties"]["ut"]["type"] == "number"
