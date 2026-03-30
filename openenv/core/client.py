"""openenv.core.client — compatibility shim.

Provides the ``EnvClient`` abstract base class that ``client.py`` sub-classes.
When openenv-core is properly installed, the real package takes precedence.
"""
from __future__ import annotations

from abc import ABC
from typing import Any


class EnvClient(ABC):
    """Minimal stub for openenv.core.client.EnvClient.

    The real implementation is provided by the openenv-core package.
    This shim exists so that ``client.py`` can be imported during testing
    without requiring openenv-core to be installed.
    """

    action_type: Any = None
    observation_type: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D107
        pass
