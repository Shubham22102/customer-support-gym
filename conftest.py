"""Root conftest.py — runs before any test module or package __init__ is imported.

Stubs openenv.core.client so the top-level __init__.py (which imports client.py
which imports openenv.core.client) does not fail during collection.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. sys.path fixup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent
for _p in [str(_PROJECT_ROOT), str(_PROJECT_ROOT / "server")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# 2. Stub openenv.core.client BEFORE the package __init__.py is imported
# ---------------------------------------------------------------------------


class _StubEnvClient:
    """Minimal stand-in for openenv.core.client.EnvClient."""

    action_type = None
    observation_type = None

    def __init__(self, *args, **kwargs):
        pass


# Build/extend the openenv module tree in sys.modules
for _mod_name in ("openenv", "openenv.core", "openenv.core.client"):
    if _mod_name not in sys.modules:
        _mod = types.ModuleType(_mod_name)
        sys.modules[_mod_name] = _mod

sys.modules["openenv.core.client"].EnvClient = _StubEnvClient  # type: ignore[attr-defined]
