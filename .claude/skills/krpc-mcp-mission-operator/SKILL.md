---
name: krpc-mcp-mission-operator
description: Use the krpc MCP server from Claude Code to safely inspect vessel state and execute KSP flight-control actions through kRPC.
---

# kRPC MCP Mission Operator Skill

Use this skill when you need Claude Code to operate KSP through the `krpc` MCP server.

## Preconditions

- KSP is running with kRPC server started.
- `krpc-mcp` is installed and registered in Claude Code.
- MCP server alias is `krpc`.

## Register MCP Server (Claude Code)

Recommended with `uv`:

```bash
claude mcp add krpc -- uvx krpc-mcp
```

Fallback:

```bash
pipx install krpc-mcp
claude mcp add krpc -- krpc-mcp
```

If needed, set:

- `KRPC_HOST` (default `127.0.0.1`)
- `KRPC_RPC_PORT` (default `50000`)
- `KRPC_STREAM_PORT` (default `50001`)

## Operating Protocol

1. Start read-only:
- `list_vessels`
- `get_vessel_info`
- `get_orbit_info`
- `get_resources`

2. Before control changes:
- Confirm target vessel (`set_active_vessel` when needed).
- State intended change and expected effect.
- Use conservative values first (e.g., low throttle).

3. Execute control actions incrementally:
- `set_throttle`
- `set_sas` / `set_rcs`
- `activate_next_stage`
- `set_autopilot_target_pitch_heading`
- `disengage_autopilot`

4. Verify after each action:
- Re-read relevant telemetry and compare against expectation.

5. On error:
- Surface exact MCP error message.
- Re-check connection/server status.
- Retry only after correcting state.

## Tool Naming Notes

`krpc-mcp` exposes tools dynamically from kRPC services using snake_case naming:

- `<service>_<procedure>`
- Example: `space_center_get_active_vessel`

For class/member procedures, pass `this` as the remote object ID returned by prior calls.

## MechJeb Notes

If `kRPC.MechJeb` is installed, MechJeb tools appear automatically with `mech_jeb_*` names.

Safe sequence:

1. Acquire handles (`mech_jeb_get_*`).
2. Configure values.
3. Enable/execute.
4. Verify vessel state/orbit updates.

## Mission Template

Use this loop for mission automation tasks:

1. Baseline: fetch vessel, orbit, and resources.
2. Plan: define next discrete control step.
3. Act: apply one command group.
4. Observe: fetch telemetry and assert expected change.
5. Repeat until objective reached.

## Handoff Template

When finishing work, report:

- What tools were called.
- What state changed in KSP.
- Final vessel/orbit/resource snapshot.
- Any residual risks (fuel, staging, attitude, comms).
