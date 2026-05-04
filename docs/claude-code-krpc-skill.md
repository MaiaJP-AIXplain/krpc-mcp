# Claude Code Skill: kRPC MCP Mission Operator

This repository includes a reusable Claude Code skill for operating KSP via this MCP server:

- Skill file: `.claude/skills/krpc-mcp-mission-operator/SKILL.md`

## Purpose

The skill standardizes how Claude Code should:

- connect to the `krpc` MCP server,
- run safe read-first workflows,
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
- plan step
- act
- observe
- repeat

## Why this matters

kRPC operations are stateful and can affect an in-flight vessel immediately. This skill provides a common operating protocol so different engineers and agents execute control actions consistently and safely.
