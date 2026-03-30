"""openenv.core.models — compatibility shim.

Provides the minimal base classes (Action, Observation, StepResult) that
mirror the openenv-core public API.  These are imported by ``models.py`` and
``server/environment.py``.

When ``openenv-core`` is installed as a proper package this shim is never
reached (the installed package has precedence on sys.path).  The shim only
activates during local development before the dependency is resolved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Action — base class for all environment actions
# ---------------------------------------------------------------------------


class Action(BaseModel):
    """Base class for structured environment actions.

    Sub-class this and add your domain-specific fields.
    All fields must be JSON-serialisable (Pydantic v2 enforces this).
    """


# ---------------------------------------------------------------------------
# Observation — base class for all environment observations
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    """Base class for structured environment observations.

    Sub-class this and add your domain-specific fields.
    All fields must be JSON-serialisable (Pydantic v2 enforces this).
    """


# ---------------------------------------------------------------------------
# StepResult — returned by Environment.step()
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """Bundles the outputs of a single environment step.

    Attributes
    ----------
    observation:
        The observation returned to the agent after the step.
    reward:
        Scalar reward signal for this step (0.0 when episode is not done;
        final cumulative reward when *done* is ``True``).
    done:
        ``True`` when the episode has terminated (either by closure or
        timeout).
    info:
        Auxiliary diagnostic information — not used for training.
    """

    observation: Observation
    reward: float = 0.0
    done: bool = False
    info: dict[str, Any] = field(default_factory=dict)
