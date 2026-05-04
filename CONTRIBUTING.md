# Contributing to krpc-mcp

Thanks for your interest in contributing! This guide covers everything you need to get started.

## How to Contribute

1. **Fork** the repository and create a branch from `main`.
2. Make your changes with clear, focused commits.
3. Ensure all tests pass and linting is clean (see below).
4. Open a pull request against `main`.

## Local Development Setup

**Prerequisites:** Python 3.11+, a running KSP instance with kRPC server mod installed (for integration tests).

```bash
# Clone your fork
git clone https://github.com/<your-username>/krpc-mcp.git
cd krpc-mcp

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest
```

Unit tests run without KSP. Integration tests require a running KSP instance; skip them with:

```bash
pytest -m "not integration"
```

### Lint and Format

```bash
# Check linting
ruff check .

# Auto-fix fixable issues
ruff check --fix .

# Format code
ruff format .
```

Ruff is configured in `pyproject.toml` (line length 100, Python 3.11 target, `E`, `F`, `I` rules).

## Pull Request Checklist

Before submitting a PR, confirm:

- [ ] Branch is up to date with `main`
- [ ] `ruff check .` passes with no errors
- [ ] `pytest` passes (or new tests added for new behavior)
- [ ] PR description explains **what** changed and **why**
- [ ] Breaking changes are called out explicitly in the PR description

## Coding Style

- Follow the ruff configuration in `pyproject.toml` — it is the style guide.
- Use type hints for all public functions and methods.
- Keep functions focused; prefer small, well-named helpers over large functions.
- Prefer explicit over implicit — avoid magic where a clear name communicates intent.

## Reporting Bugs

Open a GitHub Issue with:
- KSP version and kRPC version
- krpc-mcp version (or commit SHA)
- Minimal reproduction steps
- Expected vs. actual behavior
- Relevant log output

## Questions

Open a GitHub Discussion or drop a comment on the relevant issue.
