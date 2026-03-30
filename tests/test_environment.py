"""tests/test_environment.py — integration tests for SupportEnvironment.

Runs a complete episode against a *real* SupportEnvironment (no mocks).
Uses pytest-asyncio with asyncio_mode="auto" (configured in pyproject.toml).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Path fixup: ensure the project root is importable so that bare imports
# like `from models import ...` and `from server.xxx import ...` work.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "server"))

from models import (
    SupportAction,
    SupportObservation,
    ActionType,
    ResolutionType,
)
from server.environment import SupportEnvironment
from server.ticket_generator import TicketGenerator
from server.tool_router import ToolRouter
from server.grader import Grader
from models import PolicyRule, KBArticle


# ---------------------------------------------------------------------------
# Data-loading helpers (mirrors server/app.py helpers to stay self-contained)
# ---------------------------------------------------------------------------

_DATA_DIR = _PROJECT_ROOT / "data"


def _load_policies(path: Path) -> dict[str, PolicyRule]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_list = data.get("policies", data) if isinstance(data, dict) else data
    return {p["policy_id"]: PolicyRule(**p) for p in raw_list}


def _load_kb(path: Path) -> list[KBArticle]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_list = data.get("articles", data) if isinstance(data, dict) else data
    return [KBArticle(**a) for a in raw_list]


# ---------------------------------------------------------------------------
# Shared fixture: real SupportEnvironment backed by real data files
# ---------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path: Path) -> SupportEnvironment:
    """Build a fully-wired SupportEnvironment using real data files.

    The episodes directory is scoped to tmp_path so each test gets an
    isolated, auto-cleaned DB directory.
    """
    tickets_path = _DATA_DIR / "tickets.json"
    policies_path = _DATA_DIR / "policies.json"
    kb_path = _DATA_DIR / "knowledge_base.json"

    ticket_gen = TicketGenerator(tickets_path)
    policies = _load_policies(policies_path)
    kb = _load_kb(kb_path)

    grader = Grader()
    tool_router = ToolRouter(policies=policies, kb_articles=kb)

    episodes_dir = tmp_path / "episodes"

    return SupportEnvironment(
        ticket_generator=ticket_gen,
        tool_router=tool_router,
        grader=grader,
        episodes_dir=episodes_dir,
    )


# ---------------------------------------------------------------------------
# Convenience action builders
# ---------------------------------------------------------------------------

def _action(action_type: ActionType, **params: Any) -> SupportAction:
    return SupportAction(action_type=action_type, parameters=params)


def _lookup_order(order_id: str = "ORD-482910") -> SupportAction:
    return _action(ActionType.LOOKUP_ORDER, order_id=order_id)


def _check_policy(policy_id: str = "POL-REFUND-001") -> SupportAction:
    return _action(ActionType.CHECK_POLICY, policy_id=policy_id)


def _issue_refund(
    order_id: str = "ORD-482910",
    amount: float = 349.99,
    refund_type: str = "full",
    reason: str = "Wrong item",
) -> SupportAction:
    return _action(
        ActionType.ISSUE_REFUND,
        order_id=order_id,
        amount=amount,
        refund_type=refund_type,
        reason=reason,
    )


def _close_ticket(
    resolution: str = "refund_issued",
    summary: str = "Full refund issued for wrong item received by customer.",
) -> SupportAction:
    return _action(ActionType.CLOSE_TICKET, resolution=resolution, summary=summary)


def _send_message(
    message: str = "We are sorry to hear about your experience.",
    message_type: str = "apology",
) -> SupportAction:
    return _action(ActionType.SEND_MESSAGE, message=message, message_type=message_type)


# ---------------------------------------------------------------------------
# TEST 1: reset() returns a valid SupportObservation
# ---------------------------------------------------------------------------

async def test_reset_returns_valid_observation(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")

    assert isinstance(obs, SupportObservation)
    assert obs.step_count == 0, f"Expected step_count=0, got {obs.step_count}"
    assert obs.ticket_status.value == "open", (
        f"Expected ticket_status='open', got {obs.ticket_status}"
    )
    assert obs.sentiment_score == 0.5, (
        f"Expected sentiment_score=0.5, got {obs.sentiment_score}"
    )
    assert obs.customer_message != "", "customer_message must not be empty"
    assert obs.episode_id != "", "episode_id must not be empty"
    assert obs.max_steps == 8, f"Expected max_steps=8, got {obs.max_steps}"


# ---------------------------------------------------------------------------
# TEST 2: step() increments step_count by exactly 1
# ---------------------------------------------------------------------------

async def test_step_increments_step_count(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")
    episode_id = obs.episode_id

    result = await env.step(_lookup_order(), episode_id)

    assert result.observation.step_count == 1, (
        f"Expected step_count=1 after first step, got {result.observation.step_count}"
    )
    assert result.done is False, "Episode should not be done after one step"
    assert result.reward == 0.0, (
        f"Intermediate reward should be 0.0, got {result.reward}"
    )


# ---------------------------------------------------------------------------
# TEST 3: Timeout at max_steps returns done=True and reward=0.0
# ---------------------------------------------------------------------------

async def test_timeout_at_max_steps(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")
    episode_id = obs.episode_id

    # easy_refund has max_steps=8; send 8 no-op actions with valid params
    result = None
    for i in range(8):
        result = await env.step(
            _send_message(
                message=f"Step {i + 1}: We are processing your request, please wait.",
                message_type="update",
            ),
            episode_id,
        )

    assert result is not None
    assert result.done is True, (
        f"Episode should be done after {8} steps (timeout), done={result.done}"
    )
    assert result.reward == 0.0, (
        f"Timeout reward should be 0.0, got {result.reward}"
    )


# ---------------------------------------------------------------------------
# TEST 4: close_ticket returns done=True after the optimal 4-step path
# ---------------------------------------------------------------------------

async def test_close_ticket_returns_done_true(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")
    episode_id = obs.episode_id

    # Optimal 4-step path for easy_refund (TKT-ER0001: ORD-482910, $349.99)
    await env.step(_lookup_order("ORD-482910"), episode_id)
    await env.step(_check_policy("POL-REFUND-001"), episode_id)
    await env.step(_issue_refund("ORD-482910", 349.99, "full", "Wrong item"), episode_id)
    result = await env.step(
        _close_ticket(
            resolution="refund_issued",
            summary="Full refund issued for wrong item received by customer.",
        ),
        episode_id,
    )

    assert result.done is True, f"Expected done=True after close_ticket, got {result.done}"
    assert result.reward > 0.0, (
        f"Expected positive reward for correct resolution, got {result.reward}"
    )


# ---------------------------------------------------------------------------
# TEST 5: reward is always a float in [0.0, 1.0]
# ---------------------------------------------------------------------------

async def test_reward_is_float_in_range(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")
    episode_id = obs.episode_id

    await env.step(_lookup_order("ORD-482910"), episode_id)
    await env.step(_check_policy("POL-REFUND-001"), episode_id)
    await env.step(_issue_refund("ORD-482910", 349.99, "full", "Wrong item"), episode_id)
    result = await env.step(
        _close_ticket(
            resolution="refund_issued",
            summary="Full refund issued for wrong item received by customer.",
        ),
        episode_id,
    )

    assert isinstance(result.reward, float), (
        f"Expected reward to be float, got {type(result.reward)}"
    )
    assert 0.0 <= result.reward <= 1.0, (
        f"Reward out of range [0, 1]: {result.reward}"
    )


# ---------------------------------------------------------------------------
# TEST 6: Episode is cleaned up from _episodes after done=True
# ---------------------------------------------------------------------------

async def test_episode_cleaned_up_after_done(env: SupportEnvironment) -> None:
    obs = await env.reset("easy_refund")
    episode_id = obs.episode_id

    # Verify the episode exists before completion
    assert episode_id in env._episodes, "Episode should exist before completion"

    # Run to completion via the optimal path
    await env.step(_lookup_order("ORD-482910"), episode_id)
    await env.step(_check_policy("POL-REFUND-001"), episode_id)
    await env.step(_issue_refund("ORD-482910", 349.99, "full", "Wrong item"), episode_id)
    result = await env.step(
        _close_ticket(
            resolution="refund_issued",
            summary="Full refund issued for wrong item received by customer.",
        ),
        episode_id,
    )

    assert result.done is True, "Episode must be done before checking cleanup"
    assert episode_id not in env._episodes, (
        f"Episode {episode_id} should have been removed from env._episodes after done=True"
    )
