#!/usr/bin/env python3
"""Live kRPC control-path probe for KER-68.

Usage (from repo root):
  KRPC_HOST=127.0.0.1 KRPC_RPC_PORT=50000 KRPC_STREAM_PORT=50001 \
  .venv_qa/bin/python scripts/live_control_probe.py
"""

from __future__ import annotations

import os
import re
import socket
import sys

from krpc_mcp.bridge import KrpcBridge


def _extract_id(text: str) -> int | None:
    match = re.search(r"id=(\\d+)", text)
    return int(match.group(1)) if match else None


def _check_port(host: str, port: int) -> bool:
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main() -> int:
    host = os.environ.get("KRPC_HOST", "127.0.0.1")
    rpc_port = int(os.environ.get("KRPC_RPC_PORT", "50000"))
    stream_port = int(os.environ.get("KRPC_STREAM_PORT", "50001"))

    print(f"[probe] host={host} rpc={rpc_port} stream={stream_port}")
    rpc_open = _check_port(host, rpc_port)
    stream_open = _check_port(host, stream_port)
    print(f"[probe] rpc port open: {rpc_open}")
    print(f"[probe] stream port open: {stream_open}")
    if not (rpc_open and stream_open):
        print("[probe] FAIL: kRPC ports are not reachable from this process")
        return 2

    bridge = KrpcBridge()
    active_vessel_text = bridge.call_tool("space_center_get_active_vessel", {})[0].text
    vessel_id = _extract_id(active_vessel_text)
    print(f"[probe] active vessel: {active_vessel_text}")
    if vessel_id is None:
        print("[probe] FAIL: could not parse active vessel id")
        return 3

    wrong_chain = bridge.call_tool("space_center_control_get_throttle", {"this": vessel_id})[0].text
    print(f"[probe] control_get_throttle(this=vessel_id={vessel_id}): {wrong_chain}")

    control_text = bridge.call_tool("space_center_vessel_get_control", {"this": vessel_id})[0].text
    control_id = _extract_id(control_text)
    print(f"[probe] vessel_get_control: {control_text}")
    if control_id is None:
        print("[probe] FAIL: could not parse control id")
        return 4

    ok_chain = bridge.call_tool("space_center_control_get_throttle", {"this": control_id})[0].text
    print(f"[probe] control_get_throttle(this=control_id={control_id}): {ok_chain}")

    print("[probe] DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
