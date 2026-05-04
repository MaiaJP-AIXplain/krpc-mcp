# krpc-mcp

[![CI](https://github.com/MaiaJP-AIXplain/krpc-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/MaiaJP-AIXplain/krpc-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Model Context Protocol (MCP) server for kRPC** — lets Claude (and any MCP-compatible AI) control Kerbal Space Program through the [kRPC mod](https://krpc.github.io/krpc/).

```
KSP + kRPC mod  ←──gRPC──→  krpc-mcp server  ←──MCP──→  Claude Desktop / Claude Code
```

## Features

| Category | Tools |
|---|---|
| Vessel info | `get_vessel_info`, `list_vessels`, `set_active_vessel` |
| Flight controls | `set_throttle`, `activate_next_stage`, `set_sas`, `set_rcs`, `set_gear`, `set_brakes`, `set_autopilot_target_pitch_heading`, `disengage_autopilot` |
| Orbital mechanics | `get_orbit_info`, `add_maneuver_node`, `remove_all_maneuver_nodes`, `warp_to`, `get_universal_time` |
| Resources | `get_resources`, `get_resource_amount` |

## Requirements

- Python 3.11+
- KSP 1.x with [kRPC mod](https://krpc.github.io/krpc/) installed and the server started in-game
- An MCP host: [Claude Desktop](https://claude.ai/download) or Claude Code CLI

## Installation

```bash
pip install krpc-mcp
```

Or from source:

```bash
git clone https://github.com/MaiaJP-AIXplain/krpc-mcp
cd krpc-mcp
pip install -e .
```

## Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "krpc": {
      "command": "krpc-mcp",
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

```bash
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

A Postman Collection is included at [`docs/kRPC-Postman-Collection.json`](docs/kRPC-Postman-Collection.json) for exploring and testing the kRPC API that this MCP server wraps.

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
