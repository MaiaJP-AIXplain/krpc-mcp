# Claude Code Skill: kRPC MCP Mission Operator

This repository includes a reusable Claude Code skill for operating KSP via this MCP server:

- Skill file: `.claude/skills/krpc-mcp-mission-operator/SKILL.md`

## Purpose

The skill standardizes how Claude Code should:

- connect to the `krpc` MCP server,
- run safe read-first workflows,
- prefer MechJeb mission automation when KRPC.MechJeb is ready,
- sequence maneuver planner operations, node executor burns, and safe warps,
- apply flight-control commands incrementally,
- validate telemetry after each action,
- and hand off results clearly.

## Usage

1. Ensure `krpc-mcp` is configured in Claude Code:

```bash
claude mcp add krpc -- uvx krpc-mcp
```

2. In Claude Code, invoke or reference the skill in your workflow.

3. Follow the mission loop in the skill:
- baseline
- MechJeb readiness check
- plan step
- act
- observe
- repeat

For launch, maneuver execution, landing, docking, and rendezvous, the skill now treats MechJeb as the preferred copilot path. Direct `space_center_*` controls remain the fallback when MechJeb is not installed, not API-ready, or does not cover the specific action.

The skill includes playbooks for circularize/apoapsis/periapsis planning, MechJeb Node Executor autowarp, direct `space_center_warp_to` fallback rules, and post-action telemetry verification. For long stable coasts, warping is the default behavior instead of waiting in real time.

For broad requests like "land this vessel on Duna", agents should start with `mission_assist_plan_goal`, then execute one verified phase at a time using target-body tools, MechJeb maneuver planner operations, Node Executor autowarp, and landing autopilot.

## Why this matters

kRPC operations are stateful and can affect an in-flight vessel immediately. This skill provides a common operating protocol so different engineers and agents execute control actions consistently and safely.
