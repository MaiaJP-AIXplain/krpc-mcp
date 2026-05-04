# Operator Setup Guide (End-to-End)

This guide walks an operator from a clean machine to a verified kRPC MCP connection that can control Kerbal Space Program through an MCP host.

## Success condition

Setup is complete when all of the following are true:

1. KSP is running with the kRPC server active.
2. `krpc-mcp` starts without errors in your MCP host.
3. A prompt like "list vessels" returns live vessel data from your current save.

## 1) Prerequisites

- macOS, Windows, or Linux
- Kerbal Space Program 1.x installed
- Python 3.11+
- An MCP host (Claude Desktop or Claude Code)

Optional (for MechJeb tools):

- MechJeb2
- KRPC.MechJeb

## 2) Install KSP mods

Install these into your KSP `GameData` folder:

- kRPC
- Optional: MechJeb2
- Optional: KRPC.MechJeb (only if MechJeb MCP tools are needed)

Recommended folder layout:

```text
KSP/
  GameData/
    kRPC/
    MechJeb2/            # optional
    KRPC.MechJeb/        # optional
```

Then launch KSP and load into flight view.

## 3) Start and verify kRPC in-game

1. Open the kRPC toolbar app in KSP.
2. Start the server.
3. Confirm host/ports:
   - RPC: `50000`
   - Stream: `50001`

If your host machine differs from where the MCP process runs, set `KRPC_HOST` to the reachable address (not `127.0.0.1`).

## 4) Install `krpc-mcp`

### From PyPI

```bash
python -m pip install --upgrade pip
python -m pip install krpc-mcp
```

### From source

```bash
git clone https://github.com/MaiaJP-AIXplain/krpc-mcp
cd krpc-mcp
python -m pip install -e .
```

Sanity check:

```bash
krpc-mcp --help
```

## 5) Configure your MCP host

### Claude Desktop

Edit `claude_desktop_config.json` and add:

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

Typical config paths:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop after editing.

### Claude Code

```bash
claude mcp add krpc -- krpc-mcp
```

To override defaults in shell:

```bash
export KRPC_HOST=127.0.0.1
export KRPC_RPC_PORT=50000
export KRPC_STREAM_PORT=50001
```

## 6) Operator validation flow

Run these checks in order from your MCP host:

1. Ask: "List vessels."
2. Ask: "Get vessel info for the active vessel."
3. Ask: "Set throttle to 0.1" and verify in-game.
4. Ask: "Set throttle to 0.0" to return safe idle.

If MechJeb is installed:

1. Ask: "List available MechJeb tools."
2. Ask: "Get MechJeb ascent autopilot handle."

Expected result: tool calls succeed with live data and no connection errors.

## 7) Troubleshooting

### Cannot connect / timeout

- Confirm kRPC server is started in KSP.
- Confirm `KRPC_HOST`, `KRPC_RPC_PORT`, and `KRPC_STREAM_PORT` match kRPC settings.
- If KSP runs on another host/VM, verify firewall rules for TCP `50000` and `50001`.

### MCP host sees no `krpc` server

- Re-check MCP config JSON for syntax errors.
- Ensure `krpc-mcp` is installed in the same Python environment used by the MCP host.
- Restart the MCP host after config changes.

### MechJeb tool calls fail

- Verify MechJeb2 and KRPC.MechJeb are both installed.
- Wait until vessel scene is fully loaded before first MechJeb call.
- If returned error says API is not ready, retry after a few seconds.

## 8) Operational safety notes

- Start with read-only calls (vessel/orbit/resource queries).
- Use low throttle values for first control tests.
- Keep SAS/RCS state explicit when testing automation.
- Prefer sandbox saves while validating new mission scripts.

## 9) Handoff checklist

Before handing to another operator/engineer, confirm:

- Exact KSP mod versions used
- Active `KRPC_*` environment values
- MCP host type and version
- Whether MechJeb integrations were validated
- Any local network/firewall exceptions required
