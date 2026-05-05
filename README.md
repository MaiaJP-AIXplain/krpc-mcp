# krpc-mcp

[![CI](https://github.com/MaiaJP-AIXplain/krpc-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MaiaJP-AIXplain/krpc-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Model Context Protocol (MCP) server for kRPC** — lets Claude (and any MCP-compatible AI) control Kerbal Space Program through the [kRPC mod](https://krpc.github.io/krpc/).

```
KSP + kRPC mod  ←──gRPC──→  krpc-mcp server  ←──MCP──→  Claude Desktop / Claude Code
```

## Features

By default, `krpc-mcp` exposes a curated copilot surface: the tools an AI agent
needs for vessel state, safe control, mission planning, and MechJeb automation.
Set `KRPC_MCP_TOOL_MODE=full` when you need the low-level 1:1 kRPC API for
debugging or development.

| Category | Tools |
|---|---|
| Mission assist | `mission_assist_flight_snapshot`, `mission_assist_plan_goal` |
| Vessel/body info | `space_center_get_active_vessel`, `space_center_get_vessels`, `space_center_get_bodies`, `space_center_set_active_vessel`, `space_center_set_target_body`, `space_center_vessel_get_name`, `space_center_vessel_get_mass`, `space_center_vessel_get_situation` |
| Flight controls | `space_center_control_set_throttle`, `space_center_control_activate_next_stage`, `space_center_control_set_sas`, `space_center_control_set_rcs`, `space_center_control_set_gear`, `space_center_control_set_brakes`, `space_center_auto_pilot_target_pitch_and_heading`, `space_center_auto_pilot_disengage` |
| Orbital mechanics | `space_center_vessel_get_orbit`, `space_center_control_add_node`, `space_center_control_get_nodes`, `space_center_node_remove`, `space_center_warp_to`, `space_center_get_ut` |
| Resources | `space_center_vessel_get_resources`, `space_center_resources_get_names`, `space_center_resources_amount`, `space_center_resources_max` |

### MechJeb integration

When the [kRPC.MechJeb](https://github.com/Genhis/KRPC.MechJeb) mod is installed, mission-level agents should prefer the curated `mech_jeb_*` tools for launch, maneuver planning, node execution, landing, docking, and rendezvous. Direct `space_center_*` control remains available as a fallback.

| Category | Exposed services |
|---|---|
| Autopilots | `AscentAutopilot`, `LandingAutopilot`, `DockingAutopilot`, `RendezvousAutopilot` |
| Attitude & execution | `SmartASS` mode/interface + `Update()`, `NodeExecutor` (`ExecuteOneNode/AllNodes/Abort`) |
| Maneuver planning | `ManeuverPlanner` for circularize, apoapsis, periapsis, interplanetary transfer, transfer, plane/inclination, Lambert, and course-correction operations; `MakeNode(s)` + node execution path |
| Controllers | `ThrustController`, `StagingController`, `RCSController` |

**Safety guarantees:**
- `MechJeb.APIReady` is checked before every MechJeb tool call. If the mod is not yet initialised the server returns a clear error instead of a cryptic RPC failure.
- `OperationException` (e.g. "no target set", "invalid orbit") is caught and returned as a structured `MechJeb operation error:` message.

**Example workflow — launch to 100 km orbit:**

```
# 1. Get the AscentAutopilot handle
mech_jeb_get_ascent_autopilot → AscentAutopilot(id=42)

# 2. Configure
mech_jeb_ascent_autopilot_set_desired_orbit_altitude  this=42  value=100000
mech_jeb_ascent_autopilot_set_desired_inclination     this=42  value=0

# 3. Engage
mech_jeb_ascent_autopilot_set_enabled  this=42  value=true
```

**Example workflow — circularize at apoapsis:**

```
# 1. Get ManeuverPlanner and circularize operation
mech_jeb_get_maneuver_planner                         → ManeuverPlanner(id=10)
mech_jeb_maneuver_planner_get_operation_circularize   this=10  → OperationCircularize(id=20)

# 2. Create nodes
mech_jeb_operation_circularize_make_nodes  this=20

# 3. Execute
mech_jeb_get_node_executor                            → NodeExecutor(id=30)
mech_jeb_node_executor_set_autowarp  this=30  value=true
mech_jeb_node_executor_execute_one_node  this=30
```

## Requirements

- Python 3.11+
- KSP 1.x with one of these setups:
  - [kRPC mod](https://krpc.github.io/krpc/) installed and server started in-game
  - kRPC + [MechJeb](https://github.com/MuMech/MechJeb2) + [KRPC.MechJeb](https://github.com/Genhis/KRPC.MechJeb) (required for MechJeb MCP tools)
- An MCP host: [Claude Desktop](https://claude.ai/download) or Claude Code CLI

## Installation

### Quickstart (recommended, no manual Python env setup)

If you have [`uv`](https://docs.astral.sh/uv/), run the MCP server directly from PyPI:

```bash
claude mcp add krpc -- uvx krpc-mcp
```

This avoids a separate `pip install` step and keeps upgrades simple.

### Alternative install methods

```bash
pip install krpc-mcp
```

Or from source:

```bash
git clone https://github.com/MaiaJP-AIXplain/krpc-mcp
cd krpc-mcp
pip install -e .
```

For a full operator runbook from clean machine to validated live control, see
[`docs/operator-setup-guide.md`](docs/operator-setup-guide.md).

For a reusable Claude Code operating skill tailored to this MCP server, see
[`docs/claude-code-krpc-skill.md`](docs/claude-code-krpc-skill.md).

## Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "krpc": {
      "command": "uvx",
      "args": ["krpc-mcp"],
      "env": {
        "KRPC_HOST": "127.0.0.1",
        "KRPC_RPC_PORT": "50000",
        "KRPC_STREAM_PORT": "50001"
      }
    }
  }
}
```

### Claude Code CLI

Recommended:

```bash
claude mcp add krpc -- uvx krpc-mcp
```

Fallback (if you do not use `uv`):

```bash
pipx install krpc-mcp
claude mcp add krpc -- krpc-mcp
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `KRPC_HOST` | `127.0.0.1` | kRPC server host |
| `KRPC_RPC_PORT` | `50000` | kRPC RPC port |
| `KRPC_STREAM_PORT` | `50001` | kRPC stream port |

## Usage example

Once configured, ask Claude:

> "What is my current orbit? Add a maneuver node to raise my apoapsis to 100 km."

Claude will use `get_orbit_info` to read the current orbit, then call `add_maneuver_node` with the calculated delta-v.

## API Testing (Postman)

A Postman Collection is included at [`docs/kRPC-Postman-Collection.json`](docs/kRPC-Postman-Collection.json) for exploring and testing both supported APIs:
- base kRPC endpoints
- kRPC + KRPC.MechJeb endpoints

### Import

1. Open Postman Desktop and choose **File → Import**.
2. Select `docs/kRPC-Postman-Collection.json`.

### Protocol note

kRPC communicates via Protocol Buffers over TCP, not HTTP. The collection assumes a thin HTTP proxy that forwards POST requests to the kRPC server. A minimal proxy with `socat` or a short Python script is enough:

```bash
# Example: forward localhost:8080 → kRPC TCP at localhost:50000
python3 -c "
import http.server, urllib.request, json, socket, struct

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        # Forward body to kRPC TCP server and relay response
        # (full proxy implementation: see docs/http-proxy.md)
        self.send_response(501); self.end_headers()

http.server.HTTPServer(('', 8080), H).serve_forever()
"
```

For quick exploration without a proxy, point `{{krpc_host}}` at any HTTP wrapper or use the kRPC Python/Lua client libraries directly.

### Collection structure

| Folder | What it covers |
|---|---|
| **KRPC Core** | `GetStatus`, `GetServices`, client identity |
| **SpaceCenter / Vessel** | Active vessel, all vessels, name, MET, mass, situation, reference frame |
| **SpaceCenter / Control** | Throttle, SAS, RCS, gear, SAS mode, stage |
| **SpaceCenter / AutoPilot** | Engage/disengage, target pitch/heading/roll, error |
| **SpaceCenter / Flight** | Altitude, surface altitude, lat/lon, speed, heading, pitch, roll, G-force |
| **SpaceCenter / Orbit** | Ap/Pe altitude, eccentricity, inclination, period, time-to-Ap/Pe, SMA |
| **SpaceCenter / Resources** | Resource names, amounts and capacities |
| **MechJeb / Setup** | Get handles for SmartASS, Ascent/Landing/Rendezvous autopilots, NodeExecutor, ManeuverPlanner |
| **MechJeb / SmartASS** | Get/set interface mode and autopilot mode, Update |
| **MechJeb / Ascent Autopilot** | Enable/disable, desired altitude and inclination |
| **MechJeb / Landing Autopilot** | Land untargeted, land at position target, stop |
| **MechJeb / Node Executor** | Execute one/all nodes, abort |
| **MechJeb / Maneuver Planner** | Circularize, Hohmann, change Ap/Pe |

### Encoding helpers

All kRPC argument/return values are raw protobuf bytes base64-encoded. The collection pre-request script injects these helpers into every request via `eval(pm.collectionVariables.get('_h'))`:

```js
kRPC_encodeFloat(v)    // float32 → base64
kRPC_encodeDouble(v)   // float64 → base64
kRPC_encodeBool(v)     // bool → base64
kRPC_encodeUint64(v)   // uint64 handle → base64 varint
kRPC_encodeString(s)   // string → base64 (varint length + UTF-8)
kRPC_encodeInt32(v)    // int32/enum → base64 varint

kRPC_decodeFloat(b64)
kRPC_decodeDouble(b64)
kRPC_decodeUint64(b64)
kRPC_decodeString(b64)
kRPC_decodeInt32(b64)
```

Setup requests (Get Active Vessel, Get Control, etc.) auto-store returned handles into collection variables (`{{vessel_id}}`, `{{control_id}}`, etc.) so subsequent requests work without manual copy-paste.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/ tests/
```

## Roadmap

- [ ] Parts list and action groups
- [ ] Science experiments
- [ ] CommNet / antenna status
- [ ] Kerbal EVA control
- [ ] KSP 2 support (via kRPC-compatible fork)

## License

MIT
