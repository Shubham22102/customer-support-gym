"""conftest.py — pytest configuration for the Customer Support Gym test suite.

This conftest.py runs before any test module is imported.  It:

1.  Inserts the project root and server sub-package onto sys.path so that
    bare ``import models`` and ``from server.xxx import ...`` work.
2.  Stubs out ``openenv.core.client`` (which requires the external
    ``openenv-core`` package that is not installed in the dev environment)
    so that the top-level ``__init__.py``'s ``from .client import SupportEnv``
    does not fail during test collection.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. sys.path fixup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
for _p in [str(_PROJECT_ROOT), str(_PROJECT_ROOT / "server")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# 2. Stub openenv.core.client so client.py can be imported without the
#    real openenv-core package installed.
# ---------------------------------------------------------------------------


class _StubEnvClient:
    """Minimal stand-in for openenv.core.client.EnvClient."""

    action_type = None
    observation_type = None

    def __init__(self, *args, **kwargs):
        pass


# Build/extend the openenv module tree as needed in sys.modules
for _mod_name in ("openenv", "openenv.core", "openenv.core.client"):
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

# Expose EnvClient on the stub module
sys.modules["openenv.core.client"].EnvClient = _StubEnvClient  # type: ignore[attr-defined]

# Also ensure openenv.core.models and openenv.core.environment use the local shim
# so that imports like `from openenv.core.models import Action` still resolve
# to our local openenv/ package rather than a non-existent installed package.
# The local shim already lives at openenv/core/models.py etc.; we just need to
# make sure Python finds *our* openenv, not a missing installed one.
# The sys.path insert above achieves this — but only if we haven't already
# cached a stub for those sub-modules.  Remove any stubs we created that
# would shadow the real local shims.
for _real_mod in ("openenv.core.models", "openenv.core.environment"):
    if _real_mod in sys.modules and not hasattr(
        sys.modules[_real_mod], "__file__"
    ):
        del sys.modules[_real_mod]
