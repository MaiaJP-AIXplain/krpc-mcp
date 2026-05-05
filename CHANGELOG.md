# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-05-04

### Fixed

- **Class-member procedures now reach kRPC**, end-to-end. Every class-member tool (`Vessel_*`, `Control_*`, `AutoPilot_*`, `Flight_*`, `Orbit_*`, …) was failing in `KrpcBridge._class_proxy` because the bridge looked up generated proxy classes on the wrong target (`type(svc)` instead of the service module) and called the constructor with reversed arguments (`cls(object_id, client)` instead of `cls(client, object_id)`). Resolution now uses `sys.modules[type(svc).__module__]` for static services such as `SpaceCenter`.
- **kRPC extension services (e.g. `MechJeb`) now work**, including `ManeuverPlanner`-driven operation getters (`OperationCircularize`, `OperationApoapsis`, `OperationMoonReturn`, …). Extension services are built dynamically via kRPC's `DynamicType` machinery, so their proxy classes live as attributes on `type(svc)` rather than in a generated module — `_class_proxy` now searches both locations and rejects non-class attributes that happen to share a proxy name.

### Changed

- Test infrastructure rewritten to pin the real kRPC integration contract end-to-end. New `tests/conftest.py` provides `kspc_env` / `mechjeb_env` fixtures whose service objects carry a stable `__module__` matching real kRPC's code-gen layout, and `tests/_helpers.build_proxy()` constructs fake proxy classes with the exact `(client, object_id)` signature and Python-property setters real proxies use. `tests/test_class_proxy_contract.py` asserts both code-gen patterns end-to-end through `KrpcBridge.call_tool`, so a regression to either the wrong lookup site or the wrong constructor order fails CI loudly. Previous MagicMock-only tests silently accepted the broken contract.
- Pre-existing E501 line-length violations in `src/krpc_mcp/{bridge,connection,type_mapper}.py` and `tests/test_*.py` cleaned up; `ruff check src/ tests/` is clean for the first time since the initial commit.

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

[Unreleased]: https://github.com/MaiaJP-AIXplain/krpc-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/MaiaJP-AIXplain/krpc-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MaiaJP-AIXplain/krpc-mcp/releases/tag/v0.1.0
