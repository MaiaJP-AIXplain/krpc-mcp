# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-04

### Added

- Dynamic 1:1 kRPC bridge — MCP tools are generated at runtime from the live kRPC service introspection, so every kRPC endpoint is exposed without manual wiring
- Vessel info tools: `get_vessel_info`, `list_vessels`, `set_active_vessel`
- Flight control tools: `set_throttle`, `activate_next_stage`, `set_sas`, `set_rcs`, `set_gear`, `set_brakes`, `set_autopilot_target_pitch_heading`, `disengage_autopilot`
- Orbital mechanics tools: `get_orbit_info`, `add_maneuver_node`, `remove_all_maneuver_nodes`, `warp_to`, `get_universal_time`
- Resource tools: `get_resources`, `get_resource_amount`
- MCP server entry-point compatible with Claude Desktop and Claude Code CLI
- Environment variable configuration (`KRPC_HOST`, `KRPC_RPC_PORT`, `KRPC_STREAM_PORT`)
- Postman Collection for kRPC API exploration (`docs/kRPC-Postman-Collection.json`)
- CI pipeline with GitHub Actions (Python 3.11 and 3.12 matrix, ruff lint, pytest)
- MIT License, CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md

[Unreleased]: https://github.com/MaiaJP-AIXplain/krpc-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MaiaJP-AIXplain/krpc-mcp/releases/tag/v0.1.0
