"""Maps kRPC type descriptors to JSON Schema types and serializes return values."""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# kRPC TypeCode integer values (from KRPC.proto)
TC_NONE = 0
TC_DOUBLE = 1
TC_FLOAT = 2
TC_SINT32 = 3
TC_SINT64 = 4
TC_UINT32 = 5
TC_UINT64 = 6
TC_BOOL = 7
TC_STRING = 8
TC_BYTES = 9
TC_CLASS = 100
TC_ENUMERATION = 101
TC_EVENT = 200
TC_PROCEDURE_CALL = 201
TC_STREAM = 202
TC_STATUS = 203
TC_SERVICES = 204
TC_TUPLE = 300
TC_LIST = 301
TC_SET = 302
TC_DICTIONARY = 303

# Procedure return/param types we cannot meaningfully expose as MCP tools
SKIP_TYPE_CODES = frozenset({TC_EVENT, TC_PROCEDURE_CALL, TC_STREAM, TC_STATUS, TC_SERVICES})


def type_to_json_schema(t) -> dict:
    """Convert a kRPC Type protobuf message to a JSON Schema dict."""
    code = t.code
    if code in (TC_DOUBLE, TC_FLOAT):
        return {"type": "number"}
    if code in (TC_SINT32, TC_SINT64, TC_UINT32, TC_UINT64):
        return {"type": "integer"}
    if code == TC_BOOL:
        return {"type": "boolean"}
    if code == TC_STRING:
        return {"type": "string"}
    if code == TC_BYTES:
        return {"type": "string", "contentEncoding": "base64"}
    if code == TC_CLASS:
        return {"type": "integer", "description": f"Remote object ID ({t.service}.{t.name})"}
    if code == TC_ENUMERATION:
        return {"type": "integer", "description": f"Enum ({t.service}.{t.name})"}
    if code == TC_TUPLE:
        items = [type_to_json_schema(sub) for sub in t.types]
        return {"type": "array", "prefixItems": items, "maxItems": len(items)}
    if code == TC_LIST:
        items = type_to_json_schema(t.types[0]) if t.types else {}
        return {"type": "array", "items": items}
    if code == TC_SET:
        items = type_to_json_schema(t.types[0]) if t.types else {}
        return {"type": "array", "uniqueItems": True, "items": items}
    if code == TC_DICTIONARY:
        value_schema = type_to_json_schema(t.types[1]) if len(t.types) > 1 else {}
        return {"type": "object", "additionalProperties": value_schema}
    logger.debug("type_to_json_schema: unknown type code %r, falling back to string schema", code)
    return {"type": "string"}  # safe fallback for unknown codes


def params_to_input_schema(parameters) -> dict:
    """Build a JSON Schema input object from a kRPC procedure's parameter list."""
    properties: dict[str, dict] = {}
    required: list[str] = []

    for param in parameters:
        schema = type_to_json_schema(param.type)
        try:
            documentation = getattr(param, "documentation", "")
        except Exception:
            documentation = ""
        if documentation:
            schema = {**schema, "description": strip_xml(documentation)}
        properties[param.name] = schema
        if not param.default_value:  # empty bytes ↔ no default ↔ required
            required.append(param.name)

    result: dict = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def format_result(value: Any) -> str:
    """Serialize a kRPC return value to a human-readable string for MCP."""
    if value is None:
        return "OK"
    # kRPC class proxy — expose the remote object ID so the caller can chain calls
    if hasattr(value, "_object_id"):
        return f"{type(value).__name__}(id={value._object_id})"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return json.dumps([_as_json(v) for v in value], default=str)
    try:
        return json.dumps(_as_json(value), default=str)
    except Exception as exc:
        logger.warning(
            "format_result: JSON serialization failed for %s, falling back to str(): %s",
            type(value).__name__,
            exc,
        )
        return str(value)


def _as_json(value: Any) -> Any:
    if hasattr(value, "_object_id"):
        return {"type": type(value).__name__, "id": value._object_id}
    if isinstance(value, (bool, int, float, str, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_as_json(v) for v in value]
    logger.debug("_as_json: unhandled type %s, falling back to str()", type(value).__name__)
    return str(value)


def strip_xml(text: str) -> str:
    """Strip XML/HTML tags from kRPC documentation strings."""
    return re.sub(r"<[^>]+>", "", text).replace("\n", " ").strip()
