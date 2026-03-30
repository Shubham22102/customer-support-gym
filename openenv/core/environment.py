"""openenv.core.environment — compatibility shim.

Provides the ``Environment`` abstract base class that
``server/environment.py`` sub-classes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from openenv.core.models import Action, Observation, StepResult


class Environment(ABC):
    """Abstract base class for OpenEnv environments.

    Concrete sub-classes must implement :meth:`reset`, :meth:`step`, and
    :meth:`state`.  The :class:`~server.app.create_app` factory wraps a
    concrete implementation in a FastAPI server that exposes these three
    methods over WebSocket connections.
    """

    @abstractmethod
    async def reset(self, task_id: str = "default") -> Observation:
        """Initialise a new episode and return the first observation.

        Parameters
        ----------
        task_id:
            Identifier for the task / difficulty level to use.

        Returns
        -------
        Observation
            The initial observation presented to the agent.
        """

    @abstractmethod
    async def step(self, action: Action, episode_id: str) -> StepResult:
        """Execute *action* within an existing episode.

        Parameters
        ----------
        action:
            The action chosen by the agent for this step.
        episode_id:
            Unique identifier of the active episode to advance.

        Returns
        -------
        StepResult
            Observation, reward, done flag, and auxiliary info.
        """

    @abstractmethod
    async def state(self, episode_id: str) -> dict[str, Any]:
        """Return a serialisable snapshot of the episode's internal state.

        Parameters
        ----------
        episode_id:
            Unique identifier of the episode to inspect.

        Returns
        -------
        dict[str, Any]
            A JSON-serialisable mapping of state field names to values.
            Returns ``{"error": "Episode not found"}`` for unknown IDs.
        """
