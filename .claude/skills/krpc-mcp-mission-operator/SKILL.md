---
name: krpc-mcp-mission-operator
description: Use the krpc MCP server from Claude Code to safely inspect vessel state and execute KSP mission actions, preferring MechJeb automation when available.
---

# kRPC MCP Mission Operator Skill

Use this skill when you need Claude Code to operate KSP through the `krpc` MCP server.

## Preconditions

- KSP is running with kRPC server started.
- `krpc-mcp` is installed and registered in Claude Code.
- MCP server alias is `krpc`.
- For maneuvering, launch, landing, docking, rendezvous, and node execution, prefer MechJeb2 + KRPC.MechJeb when installed.

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
- `mission_assist_flight_snapshot`
- `mission_assist_plan_goal` for broad objectives such as "land this vessel on Duna"
- `space_center_get_active_vessel`
- `space_center_vessel_get_orbit`
- `space_center_vessel_get_resources`

2. Check MechJeb first:
- Call `mech_jeb_get_api_ready` when any mission automation is needed.
- If ready, acquire the relevant MechJeb handle before using lower-level vessel control.
- Use direct `space_center_*` control only when MechJeb is unavailable, not ready, or lacks the required capability.

3. Before control changes:
- Confirm target vessel (`space_center_set_active_vessel` when needed).
- State intended change and expected effect.
- Use conservative values first (e.g., low throttle).

4. Execute mission actions incrementally:
- Launch/ascent: prefer `mech_jeb_get_ascent_autopilot`, configure orbit target, check status, then enable.
- Maneuvers: use the maneuver playbook below; do not hand-build nodes when a MechJeb planner operation covers the request.
- Node execution: use the node executor playbook below; default to executor autowarp instead of waiting.
- Landing: prefer `mech_jeb_get_landing_autopilot`; set touchdown speed before starting when precision matters.
- Docking/rendezvous: prefer `mech_jeb_get_docking_autopilot` or `mech_jeb_get_rendezvous_autopilot`; set speed/distance limits before enabling.
- Manual fallback: use `space_center_control_set_throttle`, SAS/RCS, staging, node, warp, and autopilot target tools only when MechJeb is unavailable or unsuitable.

5. Verify after each action:
- Re-read relevant telemetry and compare against expectation.

6. On error:
- Surface exact MCP error message.
- Re-check connection/server status.
- Retry only after correcting state.

## Tool Naming Notes

`krpc-mcp` exposes tools dynamically from kRPC services using snake_case naming:

- `<service>_<procedure>`
- Example: `space_center_get_active_vessel`

For class/member procedures, pass `this` as the remote object ID returned by prior calls.

## MechJeb Notes

If `kRPC.MechJeb` is installed, MechJeb tools appear automatically with `mech_jeb_*` names. Use them as the default copilot path for mission-level work because they encode flight-domain behavior that is safer than raw throttle/attitude sequencing.

Safe sequence:

1. Confirm `mech_jeb_get_api_ready`.
2. Acquire handles (`mech_jeb_get_*`).
3. Configure values.
4. Enable/execute.
5. Verify vessel state/orbit updates with `mission_assist_flight_snapshot`.

## Maneuver Playbook

Use MechJeb's maneuver planner for orbit-shaping tasks before considering raw `space_center_control_add_node`.

1. Baseline:
- Call `mission_assist_flight_snapshot`.
- Read apoapsis, periapsis, inclination, time-to-apoapsis, time-to-periapsis, and current node handles if available.

2. Select the planner operation:
- Circularize: `mech_jeb_get_maneuver_planner` -> `mech_jeb_maneuver_planner_get_operation_circularize`.
- Raise/lower apoapsis: `mech_jeb_get_maneuver_planner` -> `mech_jeb_maneuver_planner_get_operation_apoapsis`, then set `mech_jeb_operation_apoapsis_set_new_apoapsis`.
- Raise/lower periapsis: `mech_jeb_get_maneuver_planner` -> `mech_jeb_maneuver_planner_get_operation_periapsis`, then set `mech_jeb_operation_periapsis_set_new_periapsis`.

3. Create nodes:
- Prefer `*_make_nodes` for operations that may need more than one burn.
- Use `*_make_node` only when one node is explicitly desired.
- After node creation, re-read `mission_assist_flight_snapshot` or `space_center_control_get_nodes` if available.

4. Execute nodes:
- Hand off to the Node Executor playbook.
- Do not manually throttle through a planned burn unless MechJeb execution fails or is unavailable.

5. Validate:
- After execution, re-read orbit and compare the changed element against the objective.
- If the orbit is close but outside tolerance, plan a small corrective operation instead of editing an old node blindly.

## Node Executor Playbook

Use MechJeb Node Executor for planned burns.

1. Acquire executor:
- Call `mech_jeb_get_node_executor`.
- Check `mech_jeb_node_executor_get_enabled` when available.

2. Configure warp behavior:
- Prefer `mech_jeb_node_executor_set_autowarp this=<executor> value=true` for normal future burns.
- Disable autowarp only when the user asks to wait, inspect the node first, or avoid time acceleration.

3. Execute:
- Use `mech_jeb_node_executor_execute_one_node` for the next node.
- Use `mech_jeb_node_executor_execute_all_nodes` only when the full sequence is intentional and has been reviewed.
- Use `mech_jeb_node_executor_abort` immediately if telemetry diverges, the wrong vessel is active, the target is wrong, or the user cancels.

4. Observe:
- Poll `mission_assist_flight_snapshot`.
- Watch for changed apoapsis/periapsis, speed, and time-to-node/orbit progression.
- Do not issue another executor command until the previous burn has either completed or been aborted.

## Warp Playbook

Warping is the default for long waits. Do not passively wait through large time gaps unless the user asks to watch in real time or the vessel is in a phase where warp is unsafe. Prefer MechJeb executor autowarp for maneuver nodes. Use direct kRPC warp for non-burn time skips.

1. Before direct warp:
- Confirm no active burn or imminent staging event.
- Read current universal time with `space_center_get_ut`.
- Choose an absolute target UT, not a vague duration, when calling `space_center_warp_to`.

2. Safe warp targets:
- Before apoapsis/periapsis, leave a buffer for planning and attitude settling.
- Before maneuver execution, prefer Node Executor autowarp instead of `space_center_warp_to`.
- Never warp through atmosphere, landing, docking, or active ascent unless the relevant autopilot owns the sequence.
- For long coasts in stable orbit, warp by default to the next useful event: maneuver node, apoapsis, periapsis, SOI transition, rendezvous window, or requested UT.

3. After warp:
- Re-read `mission_assist_flight_snapshot`.
- Confirm vessel, orbit, situation, and MechJeb readiness before acting.

## Direct Control Fallbacks

Use direct `space_center_*` tools for simple manual actions or when MechJeb is not available.

- Obtain handles in order: active vessel -> control/flight/orbit/resources.
- For staging, confirm throttle, altitude, and expected stage before `space_center_control_activate_next_stage`.
- For manual nodes, use `space_center_control_add_node`, inspect nodes, then prefer MechJeb Node Executor if it can execute them.
- For attitude-only control, use SAS/SmartASS before manually driving pitch/heading.
- Always return throttle to a known safe value after manual tests.

## Mission Template

Use this loop for mission automation tasks:

1. Baseline: fetch vessel, orbit, resources, and target body context.
2. Plan: call `mission_assist_plan_goal` for broad goals, then define the next discrete control step.
3. Act: apply one command group.
4. Observe: fetch telemetry and assert expected change.
5. Repeat until objective reached.

## Handoff Template

When finishing work, report:

- What tools were called.
- What state changed in KSP.
- Final vessel/orbit/resource snapshot.
- Any residual risks (fuel, staging, attitude, comms).
