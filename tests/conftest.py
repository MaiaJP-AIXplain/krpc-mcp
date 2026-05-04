"""Shared test fixtures.

The bridge resolves kRPC proxy classes against a real contract:
  1. Each generated *service* class (SpaceCenter, MechJeb, ...) lives in its
     own module under ``krpc.services``; ``conn.<snake_name>`` is an instance.
  2. Each generated *proxy* class (Vessel, Control, NodeExecutor, ...) is a
     **module-level** member of that same service module.
  3. Proxy ``__init__`` takes ``(client, object_id)``.

These fixtures recreate that exact shape so tests pin behaviour against the
real integration contract instead of MagicMock's permissiveness. A test that
mocks the wrong attribute or asserts the wrong constructor order fails
loudly here, where production code would have failed silently before.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

_FAKE_MODULE_PREFIX = "_krpc_mcp_test_"


class _ServiceProxy:
    """Tiny stand-in for a kRPC service instance.

    Behaves like a MagicMock for arbitrary attribute access (so tests can read
    e.g. ``conn.space_center.active_vessel`` without explicit setup) while
    carrying a stable ``__module__`` on its class — the property the bridge
    relies on for ``sys.modules[...]``-based proxy class lookup.

    Subclasses of ``MagicMock`` don't work here because MagicMock dynamically
    re-types each instance under ``unittest.mock``, losing the ``__module__``
    we need.
    """

    def __init__(self) -> None:
        # Hold auto-created attributes here so __getattr__ can memoise.
        # Dunder slot avoids triggering our own __setattr__ recursively.
        object.__setattr__(self, "_attrs", {})

    def __getattr__(self, name: str) -> MagicMock:
        # __getattr__ is only consulted on misses, so explicitly-set attributes
        # always shadow the auto-MagicMock fallback.
        if name.startswith("_"):
            raise AttributeError(name)
        attrs = object.__getattribute__(self, "_attrs")
        if name not in attrs:
            attrs[name] = MagicMock(name=f"<{type(self).__name__}.{name}>")
        return attrs[name]


def _build_service_env(service_class_name: str, conn_attr: str) -> types.SimpleNamespace:
    """Internal: install a fake service module + service instance on a mock conn.

    Returns a SimpleNamespace with:
      - ``conn``: a MagicMock whose ``<conn_attr>`` is the fake service.
      - ``module``: the throwaway ``types.ModuleType`` where tests register
        proxy classes by simple attribute assignment.
      - ``service_cls``: the generated service type, whose ``__module__``
        matches the fake module name (this is what makes the bridge's
        ``sys.modules[type(svc).__module__]`` lookup work).

    Caller is responsible for cleanup via ``sys.modules.pop(module.__name__)``.
    """
    module_name = f"{_FAKE_MODULE_PREFIX}{service_class_name.lower()}"
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module

    service_cls = type(service_class_name, (_ServiceProxy,), {})
    service_cls.__module__ = module_name

    conn = MagicMock()
    setattr(conn, conn_attr, service_cls())

    return types.SimpleNamespace(conn=conn, module=module, service_cls=service_cls)


@pytest.fixture
def kspc_env():
    """Fake kRPC ``SpaceCenter`` service environment.

    Usage::

        def test_something(kspc_env):
            kspc_env.module.Vessel = MyFakeVesselProxy
            kspc_env.conn.krpc.get_services.return_value = my_services_proto
            # ...
    """
    env = _build_service_env("SpaceCenter", "space_center")
    try:
        yield env
    finally:
        sys.modules.pop(env.module.__name__, None)


@pytest.fixture
def mechjeb_env():
    """Fake kRPC ``MechJeb`` service environment.

    Same shape as :func:`kspc_env`; ``env.conn.mech_jeb`` is the service
    instance, and proxy classes go on ``env.module``.
    """
    env = _build_service_env("MechJeb", "mech_jeb")
    try:
        yield env
    finally:
        sys.modules.pop(env.module.__name__, None)
