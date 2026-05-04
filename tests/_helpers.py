"""Test helpers shared across modules.

Pytest convention: ``conftest.py`` holds only fixtures; reusable utilities
that tests import directly live here.
"""

from __future__ import annotations

from typing import Any, Callable


def build_proxy(
    name: str,
    *,
    properties: dict[str, Any] | None = None,
    methods: dict[str, Callable[..., Any]] | None = None,
    instances: list | None = None,
) -> type:
    """Build a fake kRPC proxy class shaped like the real generated code.

    Real kRPC proxies:
      * Take ``(client, object_id)`` at construction.
      * Expose schema getters/setters as Python ``@property`` (so the bridge's
        ``getattr`` / ``setattr`` dispatch reaches the right hook).
      * Expose other procedures as plain methods accepting kwargs.

    Args:
        name: Class name (also surfaces in ``format_result`` output).
        properties: Map of property name → initial value, exposed as a real
            Python settable @property.
        methods: Map of method name → callable taking ``(self, **kwargs)``.
        instances: Optional list to which every constructed instance is
            appended, so tests can assert on ``(_client, _object_id)``.

    Returns:
        A newly-built class. Assign it to a service module (e.g.
        ``kspc_env.module.Vessel = build_proxy(...)``) before triggering
        bridge discovery.
    """
    properties = properties or {}
    methods = methods or {}
    captured = instances if instances is not None else []
    namespace: dict = {}

    for prop_name, default in properties.items():
        slot = f"_{prop_name}"

        def _make(slot=slot, default=default):
            def _g(self):
                return getattr(self, slot, default)

            def _s(self, value):
                setattr(self, slot, value)

            return property(_g, _s)

        namespace[prop_name] = _make()

    for m_name, fn in methods.items():
        namespace[m_name] = fn

    def _init(self, client, object_id):
        self._client = client
        self._object_id = object_id
        captured.append(self)

    namespace["__init__"] = _init
    return type(name, (), namespace)
