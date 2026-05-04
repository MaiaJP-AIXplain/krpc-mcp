"""Dynamic 1:1 kRPC → MCP bridge.

At startup, calls conn.krpc.get_services() to obtain the full kRPC service
schema, then registers one MCP tool per procedure.  Class-member procedures
(those with a leading 'this' parameter) accept an integer instance_id so the
caller can chain object references across tool calls.
"""

import logging
import re
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .connection import get_connection
from .type_mapper import SKIP_TYPE_CODES, format_result, params_to_input_schema, strip_xml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def _to_snake(name: str) -> str:
    """Convert PascalCase / camelCase / ALLCAPS to snake_case."""
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", name)
    return name.lower()


def _tool_name(service_name: str, proc_name: str) -> str:
    return f"{_to_snake(service_name)}_{_to_snake(proc_name)}"


# ---------------------------------------------------------------------------
# kRPC Python client navigation helpers
# ---------------------------------------------------------------------------

def _service_obj(conn, service_name: str):
    """Return the Python service proxy for a given kRPC service name."""
    if service_name == "KRPC":
        return conn.krpc
    return getattr(conn, _to_snake(service_name))


def _class_proxy(conn, service_name: str, class_name: str, instance_id: int):
    """Reconstruct a kRPC class proxy from its remote object ID.

    kRPC Python generates nested classes on the service type, e.g.
    type(conn.space_center).Vessel.  We instantiate with (id, conn).
    """
    svc = _service_obj(conn, service_name)
    cls = getattr(type(svc), class_name, None)
    if cls is None:
        raise AttributeError(
            f"Class {class_name!r} not found on service {service_name!r}. "
            "Ensure kRPC is running and the service is loaded."
        )
    return cls(instance_id, conn)


# ---------------------------------------------------------------------------
# Procedure invocation
# ---------------------------------------------------------------------------

def _call_on(obj, proc_name: str, rest_params, arguments: dict) -> Any:
    """Invoke a kRPC procedure via the Python client's property/method API.

    kRPC Python exposes get_X / set_X procedures as Python properties; all
    other procedures become snake_case methods.
    """
    if proc_name.startswith("get_"):
        return getattr(obj, _to_snake(proc_name[4:]))
    if proc_name.startswith("set_"):
        prop = _to_snake(proc_name[4:])
        param = rest_params[0] if rest_params else None
        value = arguments.get(param.name if param else "value")
        setattr(obj, prop, value)
        return None
    method = getattr(obj, _to_snake(proc_name))
    kwargs = {p.name: arguments[p.name] for p in rest_params if p.name in arguments}
    return method(**kwargs)


def _invoke(conn, service_name: str, proc_name: str, params: list, arguments: dict) -> Any:
    """Dispatch a single kRPC procedure call."""
    this_param = params[0] if params and params[0].name == "this" else None

    if this_param:
        class_name = this_param.type.name
        instance_id = arguments.get("this")
        if instance_id is None:
            raise ValueError("Missing required parameter 'this' (remote object ID)")
        proxy = _class_proxy(conn, service_name, class_name, int(instance_id))
        # Strip "{ClassName}_" prefix to get the bare procedure name
        prefix = f"{class_name}_"
        bare = proc_name[len(prefix):] if proc_name.startswith(prefix) else proc_name
        return _call_on(proxy, bare, params[1:], arguments)

    svc = _service_obj(conn, service_name)
    return _call_on(svc, proc_name, params, arguments)


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class KrpcBridge:
    """Discovers all kRPC procedures and wires them to an MCP Server instance."""

    def __init__(self) -> None:
        self._conn = None
        self._tools: list[Tool] = []
        # tool_name → (service_name, proc_name, param_list)
        self._registry: dict[str, tuple[str, str, list]] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _connect_and_discover(self) -> None:
        self._conn = get_connection()
        services_proto = self._conn.krpc.get_services()
        count = 0

        for service in services_proto.services:
            for proc in service.procedures:
                if not self._is_exposable(proc):
                    continue

                name = _tool_name(service.name, proc.name)
                params = list(proc.parameters)
                description = (
                    strip_xml(proc.documentation)
                    if proc.documentation
                    else f"{service.name}.{proc.name}"
                )
                input_schema = params_to_input_schema(params)

                self._tools.append(
                    Tool(
                        name=name,
                        description=description[:1024],
                        inputSchema=input_schema,
                    )
                )
                self._registry[name] = (service.name, proc.name, params)
                count += 1

        logger.info(
            "kRPC bridge: registered %d tools from %d services",
            count,
            len(services_proto.services),
        )

    @staticmethod
    def _is_exposable(proc) -> bool:
        """Return False for procedures whose types cannot be represented in MCP."""
        if proc.return_type.code in SKIP_TYPE_CODES:
            return False
        if any(p.type.code in SKIP_TYPE_CODES for p in proc.parameters):
            return False
        return True

    def _ensure_ready(self) -> None:
        if self._conn is None:
            self._connect_and_discover()

    # ------------------------------------------------------------------
    # Public API consumed by the MCP handlers
    # ------------------------------------------------------------------

    def list_tools(self) -> list[Tool]:
        self._ensure_ready()
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> list[TextContent]:
        self._ensure_ready()
        entry = self._registry.get(name)
        if entry is None:
            return [TextContent(type="text", text=f"Unknown tool: {name!r}")]
        service_name, proc_name, params = entry
        try:
            result = _invoke(self._conn, service_name, proc_name, params, arguments or {})
            return [TextContent(type="text", text=format_result(result))]
        except Exception as exc:
            logger.exception("Error invoking kRPC tool %s", name)
            return [TextContent(type="text", text=f"kRPC error: {exc}")]

    # ------------------------------------------------------------------
    # MCP Server wiring
    # ------------------------------------------------------------------

    def attach(self, server: Server) -> None:
        """Register list_tools and call_tool handlers on the given MCP Server."""
        bridge = self

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return bridge.list_tools()

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            return bridge.call_tool(name, arguments)
