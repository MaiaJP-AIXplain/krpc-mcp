"""Dynamic 1:1 kRPC → MCP bridge.

At startup, calls conn.krpc.get_services() to obtain the full kRPC service
schema, then registers one MCP tool per procedure.  Class-member procedures
(those with a leading 'this' parameter) accept an integer instance_id so the
caller can chain object references across tool calls.

Class proxy resolution: kRPC Python's code generator emits proxy classes as
top-level members of the generated service module (e.g. the ``Vessel`` class
lives at ``krpc.services.spacecenter.Vessel``, not nested on the SpaceCenter
service type), and instantiates them with ``(client, object_id)``.  We honour
that contract directly when reconstructing a proxy from a remote object ID.
"""

import logging
import os
import re
import sys
import time
from typing import Any

import krpc.error
from mcp.server import Server
from mcp.types import TextContent, Tool

from .connection import get_connection
from .type_mapper import (
    SKIP_TYPE_CODES,
    TC_EVENT,
    TC_PROCEDURE_CALL,
    TC_SERVICES,
    TC_STATUS,
    TC_STREAM,
    format_result,
    params_to_input_schema,
    strip_xml,
)

MECHJEB_SERVICE = "MechJeb"

_TYPE_CODE_NAMES: dict[int, str] = {
    TC_EVENT: "TC_EVENT",
    TC_PROCEDURE_CALL: "TC_PROCEDURE_CALL",
    TC_STREAM: "TC_STREAM",
    TC_STATUS: "TC_STATUS",
    TC_SERVICES: "TC_SERVICES",
}

logger = logging.getLogger(__name__)

_MUTATING_PREFIXES: tuple[str, ...] = (
    "set_",
    "activate",
    "warp",
    "launch",
    "recover",
    "save",
    "load",
    "quick",
    "revert",
    "dock",
    "undock",
    "decouple",
    "stage",
)


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


def _is_mutating_proc(proc_name: str) -> bool:
    """Best-effort guard for procedures that can change game state."""
    lowered = proc_name.lower()
    candidates = [lowered]
    if "_" in lowered:
        candidates.append(lowered.split("_", 1)[1])

    if any(candidate.startswith("get_") for candidate in candidates):
        return False
    return any(candidate.startswith(_MUTATING_PREFIXES) for candidate in candidates)


# ---------------------------------------------------------------------------
# MechJeb readiness guard
# ---------------------------------------------------------------------------

def _check_mechjeb_ready(conn) -> str | None:
    """Return an error string if MechJeb.APIReady is False, else None."""
    try:
        if not conn.mech_jeb.api_ready:
            return (
                "MechJeb.APIReady is false — MechJeb is not initialised. "
                "Ensure the kRPC.MechJeb mod is installed and a vessel is active."
            )
    except AttributeError:
        return "MechJeb service not found on this kRPC connection."
    return None


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

    See module docstring: kRPC's generated proxy classes live as module-level
    members of the service module and take ``(client, object_id)``.
    """
    svc = _service_obj(conn, service_name)
    module_name = type(svc).__module__
    svc_module = sys.modules.get(module_name)
    if svc_module is None:
        raise AttributeError(
            f"kRPC service module {module_name!r} for service {service_name!r} "
            "is not loaded; cannot resolve class proxies."
        )

    # Schemas occasionally report fully-qualified class names like
    # "SpaceCenter.Vessel".  The code generator only exports the leaf name, so
    # try that first; the qualified form is kept as a forward-compat fallback.
    leaf = class_name.rsplit(".", 1)[-1]
    candidates = (leaf,) if leaf == class_name else (leaf, class_name)

    for candidate in candidates:
        cls = getattr(svc_module, candidate, None)
        if cls is not None:
            return cls(conn, instance_id)

    raise AttributeError(
        f"kRPC class {class_name!r} not found in module {module_name!r} "
        f"for service {service_name!r}. "
        "For member procedures, pass the target object's handle "
        "(e.g. Vessel_get_Control returns a Control handle for Control_* calls), "
        "not a vessel handle."
    )


def _infer_class_name(this_param, proc_name: str) -> str:
    """Infer class name for a member procedure from schema metadata or procedure name."""
    t = getattr(this_param, "type", None)
    type_name = getattr(t, "name", "") if t is not None else ""
    if type_name:
        return type_name

    # Fallback for schemas that omit Type.name for the implicit "this" parameter:
    # class member procedures are named "<Class>_<Member>".
    if "_" in proc_name:
        return proc_name.split("_", 1)[0]

    raise ValueError(
        "Missing class metadata for parameter 'this': "
        "cannot infer class name from schema or procedure name."
    )


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
        class_name = _infer_class_name(this_param, proc_name)
        instance_id = arguments.get("this")
        if instance_id is None:
            raise ValueError("Missing required parameter 'this' (remote object ID)")
        proxy = _class_proxy(conn, service_name, class_name, int(instance_id))
        # Strip "<ClassName>_" prefix without depending on exact schema class-name formatting.
        bare = proc_name.split("_", 1)[1] if "_" in proc_name else proc_name
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
        skipped = 0
        service_counts: dict[str, int] = {}

        for service in services_proto.services:
            svc_count = 0
            for proc in service.procedures:
                reason = self._skip_reason(proc)
                if reason is not None:
                    logger.debug("Skipping %s.%s: %s", service.name, proc.name, reason)
                    skipped += 1
                    continue

                name = _tool_name(service.name, proc.name)
                params = list(proc.parameters)
                try:
                    documentation = getattr(proc, "documentation", "")
                except Exception:
                    documentation = ""
                description = (
                    strip_xml(documentation)
                    if documentation
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
                svc_count += 1

            if svc_count:
                service_counts[service.name] = svc_count

        if logger.isEnabledFor(logging.DEBUG):
            breakdown = ", ".join(f"{svc}: {n} tools" for svc, n in service_counts.items())
            logger.debug("kRPC bridge per-service counts: %s", breakdown)

        n_services = len(services_proto.services)
        logger.info(
            "kRPC bridge: registered %d tools from %d services (%d skipped)",
            count,
            n_services,
            skipped,
        )

    @staticmethod
    def _skip_reason(proc) -> str | None:
        """Return a human-readable skip reason if the procedure cannot be exposed, else None."""
        if proc.return_type.code in SKIP_TYPE_CODES:
            code_name = _TYPE_CODE_NAMES.get(proc.return_type.code, str(proc.return_type.code))
            return f"unsupported return type {code_name}"
        for p in proc.parameters:
            if p.type.code in SKIP_TYPE_CODES:
                code_name = _TYPE_CODE_NAMES.get(p.type.code, str(p.type.code))
                return f"unsupported param type {code_name} on '{p.name}'"
        return None

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

        read_only_mode = (
            os.environ.get("KRPC_MCP_READ_ONLY", "").strip().lower()
            in {"1", "true", "yes"}
        )
        if read_only_mode and _is_mutating_proc(proc_name):
            return [
                TextContent(
                    type="text",
                    text=(
                        f"[{name}] blocked by read-only mode: {service_name}.{proc_name} "
                        "is mutating and disabled (KRPC_MCP_READ_ONLY=1)."
                    ),
                )
            ]

        # Guard: verify MechJeb is initialised before any MechJeb call except APIReady itself.
        if service_name == MECHJEB_SERVICE and proc_name != "get_APIReady":
            err = _check_mechjeb_ready(self._conn)
            if err:
                return [TextContent(type="text", text=err)]

        logger.debug("[bridge] call_tool %s args=%s", name, list((arguments or {}).keys()))
        t0 = time.monotonic()
        try:
            result = _invoke(self._conn, service_name, proc_name, params, arguments or {})
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.debug("[bridge] call_tool %s elapsed=%dms", name, elapsed_ms)
            return [TextContent(type="text", text=format_result(result))]
        except ValueError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "[bridge] call_tool %s bad input elapsed=%dms: %s",
                name,
                elapsed_ms,
                exc,
            )
            return [TextContent(type="text", text=f"[{name}] bad input: {exc}")]
        except krpc.error.RPCError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            msg = str(exc)
            logger.error("[bridge] call_tool %s kRPC error elapsed=%dms: %s", name, elapsed_ms, msg)
            if "OperationException" in msg:
                return [TextContent(type="text", text=f"[{name}] MechJeb operation error: {msg}")]
            return [TextContent(type="text", text=f"[{name}] kRPC RPC error: {msg}")]
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.exception(
                "[bridge] call_tool %s unexpected error elapsed=%dms",
                name,
                elapsed_ms,
            )
            return [TextContent(type="text", text=f"[{name}] kRPC error: {exc}")]

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
