# Operator Release Notes (KER-54, KER-59)

Date: 2026-05-04
Scope: Fresh-install validation and release-readiness notes for `krpc-mcp`.

## QA verdict

PASS (local environment verification)

## Fresh-install path verified

Environment:
- OS: macOS (local runner)
- Python: 3.11 (virtual environment)
- Install target: editable source install from clean venv

Commands executed:

```bash
python3 -m venv .venv_qa
source .venv_qa/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
krpc-mcp --help
python -m pip check
python -m pip install -e '.[dev]'
pytest -q
```

Observed results:
- `krpc-mcp --help` returned expected CLI usage (`--debug` flag present).
- `pip check` returned `No broken requirements found.`
- Test suite result: `51 passed in 1.00s`.

## Expected vs actual behavior

- Expected: clean install succeeds, executable entry point resolves, dependency graph is healthy, and baseline test suite passes.
- Actual: all checks matched expected behavior.

## KSP in-game validation status

Partially executed against a live kRPC session (2026-05-04).

Live read-only check (direct kRPC client) passed:
- Active vessel resolved: `Hope 1`
- Vessel count resolved: `32`
- Universal time resolved: `103307151.27202673`

MCP bridge-level check failed:
- Repro: instantiate `KrpcBridge` and call `list_tools()` while kRPC server is running.
- Actual error: `AttributeError: documentation` in `src/krpc_mcp/type_mapper.py` (`params_to_input_schema`).
- Impact: MCP dynamic tool discovery can fail before exposing tools.

Release sign-off status:
- MCP bridge blocker resolved in KER-60 (discovery now succeeds in live probe).
- Packaging blocker resolved in KER-62 (`python -m build` succeeds with `.venv_qa` present).
- Runtime control-path blocker remains open (follow-up after KER-66 completion: KER-68).

## Release-readiness operator checklist

1. Confirm tag/version alignment (`pyproject.toml` version, changelog section, git tag).
2. Build distributable artifacts from clean source (`python -m build`).
3. Verify wheels/sdist do not include local/dev-only files.
4. Confirm operator docs are current:
   - `docs/operator-setup-guide.md`
   - `docs/operator-release-notes.md`
5. Obtain CTO approval on release issue before publication.

## Release-channel notes

- This repository currently ships as a Python package; no `.netkan` descriptor, `GameData` package tree, or `MiniAVC` `.version` artifact exists in this codebase.
- If CKAN/KSP-native packaging is required later, track it as a dedicated follow-up issue before release.

## Additional release blocker found in KER-59

Build artifact generation failed on 2026-05-04:
- Repro: run `python -m build` from repo root.
- Actual error: `tarfile.AbsoluteLinkError: 'krpc_mcp-0.1.0/.venv_qa/bin/python3.11' is a link to an absolute path`.
- Impact: clean release artifacts (wheel/sdist) cannot currently be produced for publication.

Re-validation after KER-61 completion (same date) still fails with equivalent error:
- `tarfile.AbsoluteLinkError: 'krpc_mcp-0.1.0/.venv_qa/bin/python3.14' is a link to an absolute path`.
- Current exclusions in `pyproject.toml` cover `.venv`, `venv`, `.env`, but not `.venv_qa`.

## New runtime blocker found in KER-59 final sign-off run

- Control tools are discoverable (`space_center_control_get_throttle`, `space_center_control_set_throttle`) but fail at runtime.
- Repro:
  1. Call `space_center_get_active_vessel` (returns `Vessel(id=32)`).
  2. Call `space_center_control_get_throttle` with `this=32`.
  3. Call `space_center_control_set_throttle` with `this=32`, `value=0.1`.
- Actual:
  - `Class 'Control' not found on service 'SpaceCenter'. Ensure kRPC is running and the service is loaded.`
- Impact:
  - Live control safety validation cannot pass until class-proxy resolution for member procedures is fixed.

Re-check after KER-64 and KER-66 marked done:
- Read-path still passes (`space_center_get_ut`, `space_center_get_vessels`, `space_center_get_active_vessel`).
- Control-path still fails with same error for both throttle and SAS calls.
- KER-64/KER-66 completion did not resolve runtime behavior in this QA environment; regression follow-up tracked in KER-68.
