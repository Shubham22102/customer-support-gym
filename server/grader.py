from __future__ import annotations

from typing import Any

from models import EpisodeConfig, ResolutionType, TicketState

# ---------------------------------------------------------------------------
# Resolution family membership
# ---------------------------------------------------------------------------

_REFUND_FAMILY: frozenset[ResolutionType] = frozenset(
    {
        ResolutionType.REFUND_ISSUED,
        ResolutionType.PARTIAL_REFUND_ISSUED,
        ResolutionType.COMPENSATION_ISSUED,
    }
)

_SHIPPING_FAMILY: frozenset[ResolutionType] = frozenset(
    {
        ResolutionType.REPLACEMENT_SHIPPED,
        ResolutionType.REFUND_ISSUED,
    }
)

_ESCALATION_FAMILY: frozenset[ResolutionType] = frozenset(
    {
        ResolutionType.ESCALATED,
    }
)

_ACCOUNT_FAMILY: frozenset[ResolutionType] = frozenset(
    {
        ResolutionType.ACCOUNT_UNLOCKED,
        ResolutionType.INFORMATION_PROVIDED,
    }
)

_INFO_FAMILY: frozenset[ResolutionType] = frozenset(
    {
        ResolutionType.INFORMATION_PROVIDED,
        ResolutionType.NO_ACTION_REQUIRED,
    }
)

_ALL_FAMILIES: list[frozenset[ResolutionType]] = [
    _REFUND_FAMILY,
    _SHIPPING_FAMILY,
    _ESCALATION_FAMILY,
    _ACCOUNT_FAMILY,
    _INFO_FAMILY,
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolution_match_score(agent: ResolutionType, ground: ResolutionType) -> float:
    """Return 1.0 for exact match, 0.4 for same family, 0.0 otherwise."""
    if agent == ground:
        return 1.0

    for family in _ALL_FAMILIES:
        if agent in family and ground in family:
            return 0.4

    return 0.0


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------


def compute_resolution_score(state: TicketState, config: EpisodeConfig) -> float:
    """Compute resolution quality score in [0, 1]."""
    if state.timeout_flag:
        return 0.0

    if state.resolution is None:
        return 0.0

    base = _resolution_match_score(state.resolution, config.ground_truth_resolution)

    if config.task_id == "multi_issue":
        coverage = len(set(state.issues_resolved) & set(config.issue_types)) / len(
            config.issue_types
        )
        return round(base * coverage, 4)

    return round(base, 4)


def compute_efficiency_score(state: TicketState, config: EpisodeConfig) -> float:
    """Compute step-efficiency score in [0, 1]."""
    if state.timeout_flag:
        return 0.0

    if state.step_count <= 0:
        return 0.0

    optimal = config.optimal_steps
    actual = state.step_count

    if actual <= optimal:
        return 1.0

    budget = config.max_steps - optimal
    if budget <= 0:
        return 1.0

    excess = actual - optimal
    score = 1.0 - (excess / budget)
    return round(max(0.0, score), 4)


def compute_compliance_score(state: TicketState, config: EpisodeConfig) -> float:
    """Compute policy-compliance score in [0, 1]."""
    applicable = config.applicable_policy_ids

    if not applicable:
        return 1.0

    violated_applicable = [p for p in applicable if p in state.policy_violations]
    n_respected = len(applicable) - len(violated_applicable)
    score = n_respected / len(applicable)
    return round(max(0.0, score), 4)


def compute_sentiment_score(state: TicketState) -> float:
    """Compute customer sentiment score in [0, 1]."""
    return round(max(0.0, min(1.0, state.customer_sentiment)), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score(
    state: TicketState, config: EpisodeConfig
) -> tuple[float, dict[str, Any]]:
    """Compute final reward for a completed episode.

    Parameters
    ----------
    state:
        Read-only snapshot of the episode's terminal ``TicketState``.
    config:
        The ``EpisodeConfig`` that drove this episode.

    Returns
    -------
    tuple[float, dict[str, Any]]
        ``(reward, info)`` where *reward* is clamped to ``[0.0, 1.0]`` and
        *info* contains per-component breakdown details.
    """
    if state.timeout_flag:
        return 0.0, {
            "resolution_score": 0.0,
            "efficiency_score": 0.0,
            "compliance_score": 0.0,
            "sentiment_score": round(state.customer_sentiment, 4),
            "final_reward": 0.0,
            "ground_truth_resolution": config.ground_truth_resolution.value,
            "agent_resolution": None,
            "policy_violations": list(state.policy_violations),
            "timeout": True,
        }

    R = compute_resolution_score(state, config)
    E = compute_efficiency_score(state, config)
    C = compute_compliance_score(state, config)
    S = compute_sentiment_score(state)

    raw = (R * 0.55) + (E * 0.20) + (C * 0.15) + (S * 0.10)
    reward = round(max(0.0, min(1.0, raw)), 4)

    return reward, {
        "resolution_score": R,
        "efficiency_score": E,
        "compliance_score": C,
        "sentiment_score": S,
        "final_reward": reward,
        "ground_truth_resolution": config.ground_truth_resolution.value,
        "agent_resolution": state.resolution.value if state.resolution else None,
        "policy_violations": list(state.policy_violations),
        "timeout": False,
    }


# ---------------------------------------------------------------------------
# Grader class — thin wrapper so environment.py can hold an instance
# ---------------------------------------------------------------------------


class Grader:
    """Stateless wrapper around the module-level :func:`score` function.

    ``environment.py`` receives a ``Grader`` instance at construction time
    and calls ``self._grader.score(state, config)``.  This class delegates
    directly to the pure-function implementation above so that the grader
    remains side-effect-free.
    """

    def score(
        self,
        state: TicketState,
        config: EpisodeConfig,
    ) -> tuple[float, dict[str, Any]]:
        """Compute final reward for a completed episode.

        Delegates to the module-level :func:`score` function.

        Parameters
        ----------
        state:
            Terminal ``TicketState`` after ``done=True``.
        config:
            The ``EpisodeConfig`` that drove the episode.

        Returns
        -------
        tuple[float, dict[str, Any]]
            ``(final_reward, breakdown_dict)`` as specified in
            ``REWARD_SPEC.md``.
        """
        return score(state, config)
