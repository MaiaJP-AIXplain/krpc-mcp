# krpc-mcp

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
