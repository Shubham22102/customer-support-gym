"""tests/test_grader.py — unit tests for server/grader.py

Canonical test vectors for the Customer Support Resolution Gym reward function.
Uses pytest-asyncio with asyncio_mode="auto" (configured in pyproject.toml).
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path fixup: ensure the project root is importable so that bare imports
# like `from models import ...` work when pytest is run from the repo root.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "server"))

import pytest

from models import (
    EpisodeConfig,
    TicketState,
    ResolutionType,
    IssueType,
    IssueCategory,
    TaskDifficulty,
    DBSeed,
    CustomerRecord,
    OrderRecord,
    OrderItem,
    ShippingAddress,
    ProductRecord,
    AccountStatus,
    LoyaltyTier,
    OrderStatus,
    PaymentMethod,
)
from server.grader import Grader, score


# ---------------------------------------------------------------------------
# Helpers: minimal valid object builders
# ---------------------------------------------------------------------------

def _minimal_db_seed() -> DBSeed:
    """Build a minimal but valid DBSeed."""
    customer = CustomerRecord(
        customer_id="CUST-TEST",
        name="Test User",
        email="test@example.com",
        account_status=AccountStatus.ACTIVE,
        loyalty_tier=LoyaltyTier.STANDARD,
        order_history=["ORD-TEST001"],
        total_lifetime_spend=100.0,
        open_disputes=0,
    )
    order = OrderRecord(
        order_id="ORD-TEST001",
        customer_id="CUST-TEST",
        items=[
            OrderItem(sku="SKU-TEST", name="Test Product", quantity=1, unit_price=50.0)
        ],
        status=OrderStatus.DELIVERED,
        total_amount=50.0,
        payment_method=PaymentMethod.CREDIT_CARD,
        created_at="2026-03-01T10:00:00Z",
        shipped_at="2026-03-02T10:00:00Z",
        delivered_at="2026-03-05T10:00:00Z",
        tracking_number="TRACK001",
        shipping_address=ShippingAddress(
            street="1 Test St", city="Testville", state="CA", zip="90001"
        ),
        fraud_flagged=False,
    )
    product = ProductRecord(
        sku="SKU-TEST",
        name="Test Product",
        category="electronics",  # type: ignore[arg-type]
        price=50.0,
        weight_kg=0.5,
    )
    return DBSeed(customers=[customer], orders=[order], products=[product])


def make_state(**kwargs) -> TicketState:
    """Create a minimal valid TicketState with sensible defaults.

    Any keyword argument overrides the corresponding field.
    """
    defaults: dict = {
        "episode_id": "test-episode-001",
        "task_id": "easy_refund",
        "ticket_id": "TKT-TEST001",
        "step_count": 4,
        "max_steps": 8,
        "customer_sentiment": 0.75,
        "resolution": ResolutionType.REFUND_ISSUED,
        "issues_resolved": [IssueType.WRONG_ITEM_RECEIVED],
        "policy_violations": [],
        "timeout_flag": False,
        "escalated": False,
    }
    defaults.update(kwargs)
    return TicketState(**defaults)


def make_config(**kwargs) -> EpisodeConfig:
    """Create a minimal valid EpisodeConfig with sensible defaults.

    Any keyword argument overrides the corresponding field.
    """
    defaults: dict = {
        "ticket_id": "TKT-TEST001",
        "task_id": "easy_refund",
        "difficulty": TaskDifficulty.EASY,
        "max_steps": 8,
        "optimal_steps": 4,
        "category": IssueCategory.PRODUCT,
        "issue_types": [IssueType.WRONG_ITEM_RECEIVED],
        "opening_message": "I received the wrong item.",
        "ground_truth_resolution": ResolutionType.REFUND_ISSUED,
        "applicable_policy_ids": ["POL-REFUND-001"],
        "customer_id": "CUST-TEST",
        "order_ids": ["ORD-TEST001"],
        "fraud_flag": False,
        "customer_replies": {"order_id": "ORD-TEST001"},
        "trap_actions": [],
        "db_seed": _minimal_db_seed(),
    }
    defaults.update(kwargs)
    return EpisodeConfig(**defaults)


# ---------------------------------------------------------------------------
# Test fixtures / shared grader instance
# ---------------------------------------------------------------------------

@pytest.fixture
def grader() -> Grader:
    return Grader()


# ---------------------------------------------------------------------------
# TEST 1: Perfect easy_refund → reward == 0.975
#
# R=1.0, E=1.0, C=1.0, S=0.75
# raw = 1.0*0.55 + 1.0*0.20 + 1.0*0.15 + 0.75*0.10 = 0.55+0.20+0.15+0.075 = 0.975
# ---------------------------------------------------------------------------

async def test_perfect_easy_refund_reward(grader: Grader) -> None:
    state = make_state(
        step_count=4,
        max_steps=8,
        customer_sentiment=0.75,
        resolution=ResolutionType.REFUND_ISSUED,
        issues_resolved=[IssueType.WRONG_ITEM_RECEIVED],
        policy_violations=[],
        timeout_flag=False,
        escalated=False,
    )
    config = make_config(
        task_id="easy_refund",
        optimal_steps=4,
        max_steps=8,
        ground_truth_resolution=ResolutionType.REFUND_ISSUED,
        applicable_policy_ids=["POL-REFUND-001"],
    )
    reward, breakdown = grader.score(state, config)
    assert reward == 0.975, f"Expected 0.975, got {reward}"


# ---------------------------------------------------------------------------
# TEST 2: Timeout always returns 0.0
# ---------------------------------------------------------------------------

async def test_timeout_returns_zero(grader: Grader) -> None:
    state = make_state(timeout_flag=True, step_count=8)
    config = make_config()
    reward, breakdown = grader.score(state, config)
    assert reward == 0.0, f"Expected 0.0 on timeout, got {reward}"
    assert breakdown["timeout"] is True, "Expected breakdown['timeout'] == True"


# ---------------------------------------------------------------------------
# TEST 3: Wrong resolution same family (partial_refund vs refund) → R=0.4
#
# R=0.4, E=1.0 (step_count defaults to 4, optimal=4), C=1.0 (no policies),
# S=0.75 (default sentinel)
# raw = 0.4*0.55 + 1.0*0.20 + 1.0*0.15 + 0.75*0.10
#     = 0.22   + 0.20   + 0.15   + 0.075
#     = 0.645
# ---------------------------------------------------------------------------

async def test_wrong_resolution_same_family(grader: Grader) -> None:
    state = make_state(
        resolution=ResolutionType.PARTIAL_REFUND_ISSUED,
        policy_violations=[],
        customer_sentiment=0.75,
        step_count=4,
    )
    config = make_config(
        ground_truth_resolution=ResolutionType.REFUND_ISSUED,
        applicable_policy_ids=[],
        optimal_steps=4,
        max_steps=8,
    )
    reward, breakdown = grader.score(state, config)
    assert abs(reward - 0.645) < 0.001, (
        f"Expected reward ≈ 0.645 (R=0.4, same-family partial), got {reward}"
    )


# ---------------------------------------------------------------------------
# TEST 4: Policy violation reduces C by 50%
#
# applicable=[POL-FRAUD-001, POL-REFUND-001], violated=[POL-FRAUD-001]
# C = (2 - 1) / 2 = 0.5
# ---------------------------------------------------------------------------

async def test_policy_violation_reduces_compliance(grader: Grader) -> None:
    state = make_state(policy_violations=["POL-FRAUD-001"])
    config = make_config(
        applicable_policy_ids=["POL-FRAUD-001", "POL-REFUND-001"]
    )
    _, breakdown = grader.score(state, config)
    assert breakdown["compliance_score"] == 0.5, (
        f"Expected compliance_score=0.5, got {breakdown['compliance_score']}"
    )


# ---------------------------------------------------------------------------
# TEST 5: Reward is always a float
# ---------------------------------------------------------------------------

async def test_reward_is_float(grader: Grader) -> None:
    state = make_state()
    config = make_config()
    reward, _ = grader.score(state, config)
    assert isinstance(reward, float), f"Expected float, got {type(reward)}"


# ---------------------------------------------------------------------------
# TEST 6: Reward never exceeds 1.0
#
# Use maximum sentiment and no violations with a perfect resolution.
# ---------------------------------------------------------------------------

async def test_reward_never_exceeds_one(grader: Grader) -> None:
    state = make_state(
        customer_sentiment=1.0,
        policy_violations=[],
        resolution=ResolutionType.REFUND_ISSUED,
        step_count=4,
    )
    config = make_config(
        ground_truth_resolution=ResolutionType.REFUND_ISSUED,
        applicable_policy_ids=["POL-REFUND-001"],
        optimal_steps=4,
        max_steps=8,
    )
    reward, _ = grader.score(state, config)
    assert 0.0 <= reward <= 1.0, f"Reward out of range [0, 1]: {reward}"


# ---------------------------------------------------------------------------
# TEST 7: Efficiency degrades linearly — easy_refund 6 steps → E=0.5
#
# optimal=4, max=8, actual=6
# budget = 8 - 4 = 4
# excess = 6 - 4 = 2
# E = 1 - 2/4 = 0.5
# ---------------------------------------------------------------------------

async def test_efficiency_degrades_linearly(grader: Grader) -> None:
    state = make_state(step_count=6)
    config = make_config(optimal_steps=4, max_steps=8)
    _, breakdown = grader.score(state, config)
    assert breakdown["efficiency_score"] == 0.5, (
        f"Expected efficiency_score=0.5 for 6 steps (opt=4, max=8), "
        f"got {breakdown['efficiency_score']}"
    )


# ---------------------------------------------------------------------------
# TEST 8: Wrong resolution completely different family → R=0.0
#
# escalated is in _ESCALATION_FAMILY, refund_issued is in _REFUND_FAMILY only
# (no overlap), so resolution_score must be 0.0.
# ---------------------------------------------------------------------------

async def test_wrong_resolution_different_family(grader: Grader) -> None:
    state = make_state(resolution=ResolutionType.ESCALATED)
    config = make_config(ground_truth_resolution=ResolutionType.REFUND_ISSUED)
    _, breakdown = grader.score(state, config)
    assert breakdown["resolution_score"] == 0.0, (
        f"Expected resolution_score=0.0 for cross-family mismatch, "
        f"got {breakdown['resolution_score']}"
    )


# ---------------------------------------------------------------------------
# TEST 9: multi_issue partial coverage → R = base * coverage
#
# task_id="multi_issue", resolution=MULTIPLE_RESOLUTIONS (exact match → base=1.0)
# issue_types = [ACCOUNT_LOCKED, UNAUTHORIZED_TRANSACTION, LATE_DELIVERY]  (3 total)
# issues_resolved = [ACCOUNT_LOCKED, LATE_DELIVERY]  (2 of 3)
# coverage = 2/3
# R = round(1.0 * 2/3, 4) = 0.6667
# ---------------------------------------------------------------------------

async def test_multi_issue_partial_coverage(grader: Grader) -> None:
    state = make_state(
        task_id="multi_issue",
        resolution=ResolutionType.MULTIPLE_RESOLUTIONS,
        issues_resolved=[IssueType.ACCOUNT_LOCKED, IssueType.LATE_DELIVERY],
    )
    config = make_config(
        task_id="multi_issue",
        ground_truth_resolution=ResolutionType.MULTIPLE_RESOLUTIONS,
        issue_types=[
            IssueType.ACCOUNT_LOCKED,
            IssueType.UNAUTHORIZED_TRANSACTION,
            IssueType.LATE_DELIVERY,
        ],
    )
    _, breakdown = grader.score(state, config)
    expected = round(1.0 * (2 / 3), 4)
    assert breakdown["resolution_score"] == expected, (
        f"Expected resolution_score={expected} for 2/3 coverage, "
        f"got {breakdown['resolution_score']}"
    )


# ---------------------------------------------------------------------------
# TEST 10: Breakdown dict has all required keys
# ---------------------------------------------------------------------------

async def test_breakdown_has_all_required_keys(grader: Grader) -> None:
    required_keys = {
        "resolution_score",
        "efficiency_score",
        "compliance_score",
        "sentiment_score",
        "final_reward",
        "ground_truth_resolution",
        "agent_resolution",
        "policy_violations",
        "timeout",
    }
    state = make_state()
    config = make_config()
    _, breakdown = grader.score(state, config)
    missing = required_keys - set(breakdown.keys())
    assert not missing, f"Breakdown missing keys: {missing}"
