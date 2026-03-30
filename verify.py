"""verify.py — Pre-submission verification for the Customer Support Resolution Gym.

Run with:
    .venv/bin/python verify.py

Prints PASS / FAIL for each of 8 checks and a final summary.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — must happen before any project import
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent
for _p in [str(_ROOT), str(_ROOT / "server")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# openenv shim — use the real local openenv/ package if present on sys.path;
# only fall back to a minimal stub when it is genuinely missing.
# This avoids clobbering openenv.core as a package (which would block
# the import of openenv.core.models, openenv.core.environment, etc.)
# ---------------------------------------------------------------------------
try:
    import openenv.core.client  # noqa: F401 — real local shim at openenv/core/client.py
except ModuleNotFoundError:
    # Build the minimal stub tree without replacing already-imported sub-packages
    for _mod_name in ("openenv", "openenv.core", "openenv.core.client"):
        if _mod_name not in sys.modules:
            sys.modules[_mod_name] = types.ModuleType(_mod_name)

    class _StubEnvClient:
        action_type = None
        observation_type = None

        def __init__(self, *args, **kwargs):
            pass

    sys.modules["openenv.core.client"].EnvClient = _StubEnvClient  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# Colour helpers (degrade gracefully when stdout is not a TTY)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()
_GREEN = "\033[92m" if _USE_COLOR else ""
_RED = "\033[91m" if _USE_COLOR else ""
_BOLD = "\033[1m" if _USE_COLOR else ""
_RESET = "\033[0m" if _USE_COLOR else ""


def _pass(label: str) -> None:
    print(f"  {_GREEN}PASS{_RESET}  {label}")


def _fail(label: str, err: Exception) -> None:
    print(f"  {_RED}FAIL{_RESET}  {label}")
    print(f"         {_RED}{type(err).__name__}: {err}{_RESET}")


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------
_results: dict[int, bool] = {}


def _run(num: int, label: str, fn) -> None:
    """Execute a sync or async check and record the result."""
    try:
        if inspect.iscoroutinefunction(fn):
            asyncio.run(fn())
        else:
            fn()
        _pass(label)
        _results[num] = True
    except Exception as exc:  # noqa: BLE001
        _fail(label, exc)
        _results[num] = False


# ---------------------------------------------------------------------------
# CHECK 1: Models import cleanly
# ---------------------------------------------------------------------------
def check_1() -> None:
    from models import SupportAction, SupportObservation, TicketState, EpisodeConfig  # noqa: F401
    action = SupportAction(
        action_type="lookup_order",
        parameters={"order_id": "ORD-123"},
    )
    assert action.parameters["order_id"] == "ORD-123"


# ---------------------------------------------------------------------------
# CHECK 2: Data files are valid JSON with correct structure
# ---------------------------------------------------------------------------
def check_2() -> None:
    _DATA = _ROOT / "data"

    tickets_raw = json.loads((_DATA / "tickets.json").read_text(encoding="utf-8"))
    assert "tickets" in tickets_raw, "Missing 'tickets' key in tickets.json"
    assert len(tickets_raw["tickets"]) >= 3, (
        f"Expected ≥3 tickets, got {len(tickets_raw['tickets'])}"
    )

    policies_raw = json.loads((_DATA / "policies.json").read_text(encoding="utf-8"))
    policies_list = policies_raw.get("policies", policies_raw)
    assert len(policies_list) >= 10, (
        f"Expected ≥10 policies, got {len(policies_list)}"
    )

    kb_raw = json.loads((_DATA / "knowledge_base.json").read_text(encoding="utf-8"))
    articles_list = kb_raw.get("articles", kb_raw)
    assert len(articles_list) >= 15, (
        f"Expected ≥15 KB articles, got {len(articles_list)}"
    )


# ---------------------------------------------------------------------------
# CHECK 3: TicketGenerator loads all required task configs
# ---------------------------------------------------------------------------
def check_3() -> None:
    from server.ticket_generator import TicketGenerator
    from models import EpisodeConfig

    gen = TicketGenerator(_ROOT / "data" / "tickets.json")
    for task_id in ("easy_refund", "billing_dispute", "multi_issue"):
        cfg = gen.get_config(task_id)
        assert isinstance(cfg, EpisodeConfig), (
            f"get_config('{task_id}') returned {type(cfg)}, expected EpisodeConfig"
        )


# ---------------------------------------------------------------------------
# CHECK 4: Grader produces the known 0.975 reward for perfect easy_refund
# ---------------------------------------------------------------------------
def check_4() -> None:
    from models import (
        TicketState,
        EpisodeConfig,
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
    from server.grader import Grader

    db_seed = DBSeed(
        customers=[
            CustomerRecord(
                customer_id="CUST-V001",
                name="Verify User",
                email="verify@example.com",
                account_status=AccountStatus.ACTIVE,
                loyalty_tier=LoyaltyTier.STANDARD,
                order_history=["ORD-V001"],
                total_lifetime_spend=349.99,
                open_disputes=0,
            )
        ],
        orders=[
            OrderRecord(
                order_id="ORD-V001",
                customer_id="CUST-V001",
                items=[OrderItem(sku="SKU-V1", name="Blender", quantity=1, unit_price=349.99)],
                status=OrderStatus.DELIVERED,
                total_amount=349.99,
                payment_method=PaymentMethod.CREDIT_CARD,
                created_at="2026-02-01T10:00:00Z",
                shipped_at="2026-02-02T10:00:00Z",
                delivered_at="2026-02-05T10:00:00Z",
                tracking_number="TRACK-V001",
                shipping_address=ShippingAddress(
                    street="1 Main St", city="Springfield", state="IL", zip="62701"
                ),
                fraud_flagged=False,
            )
        ],
        products=[
            ProductRecord(
                sku="SKU-V1",
                name="Blender",
                category="electronics",
                price=349.99,
                weight_kg=1.2,
            )
        ],
    )

    state = TicketState(
        episode_id="verify-001",
        task_id="easy_refund",
        ticket_id="TKT-V001",
        step_count=4,
        max_steps=8,
        customer_sentiment=0.75,
        resolution=ResolutionType.REFUND_ISSUED,
        issues_resolved=[IssueType.WRONG_ITEM_RECEIVED],
        policy_violations=[],
        timeout_flag=False,
        escalated=False,
    )
    config = EpisodeConfig(
        ticket_id="TKT-V001",
        task_id="easy_refund",
        difficulty=TaskDifficulty.EASY,
        max_steps=8,
        optimal_steps=4,
        category=IssueCategory.PRODUCT,
        issue_types=[IssueType.WRONG_ITEM_RECEIVED],
        opening_message="I received the wrong item.",
        ground_truth_resolution=ResolutionType.REFUND_ISSUED,
        applicable_policy_ids=["POL-REFUND-001"],
        customer_id="CUST-V001",
        order_ids=["ORD-V001"],
        fraud_flag=False,
        customer_replies={"order_id": "ORD-V001"},
        trap_actions=[],
        db_seed=db_seed,
    )

    reward, _ = Grader().score(state, config)
    assert reward == 0.975, f"Expected 0.975, got {reward}"


# ---------------------------------------------------------------------------
# CHECK 5: Reward is always float in [0.0, 1.0] across 5 varied inputs
# ---------------------------------------------------------------------------
def check_5() -> None:
    from models import (
        TicketState,
        EpisodeConfig,
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
    from server.grader import Grader

    def _seed() -> DBSeed:
        return DBSeed(
            customers=[CustomerRecord(
                customer_id="C1", name="A", email="a@a.com",
                account_status=AccountStatus.ACTIVE, loyalty_tier=LoyaltyTier.STANDARD,
                order_history=["O1"], total_lifetime_spend=50.0, open_disputes=0,
            )],
            orders=[OrderRecord(
                order_id="O1", customer_id="C1",
                items=[OrderItem(sku="S1", name="X", quantity=1, unit_price=50.0)],
                status=OrderStatus.DELIVERED, total_amount=50.0,
                payment_method=PaymentMethod.CREDIT_CARD,
                created_at="2026-01-01T00:00:00Z", shipped_at="2026-01-02T00:00:00Z",
                delivered_at="2026-01-03T00:00:00Z", tracking_number="T1",
                shipping_address=ShippingAddress(street="1 A", city="B", state="C", zip="00000"),
                fraud_flagged=False,
            )],
            products=[ProductRecord(
                sku="S1", name="X", category="electronics", price=50.0, weight_kg=0.1,
            )],
        )

    def _cfg(**kw) -> EpisodeConfig:
        d = dict(
            ticket_id="T1", task_id="easy_refund", difficulty=TaskDifficulty.EASY,
            max_steps=8, optimal_steps=4, category=IssueCategory.PRODUCT,
            issue_types=[IssueType.WRONG_ITEM_RECEIVED], opening_message="Help.",
            ground_truth_resolution=ResolutionType.REFUND_ISSUED,
            applicable_policy_ids=["POL-REFUND-001"],
            customer_id="C1", order_ids=["O1"], fraud_flag=False,
            customer_replies={}, trap_actions=[], db_seed=_seed(),
        )
        d.update(kw)
        return EpisodeConfig(**d)

    def _state(**kw) -> TicketState:
        d = dict(
            episode_id="e1", task_id="easy_refund", ticket_id="T1",
            step_count=4, max_steps=8, customer_sentiment=0.75,
            resolution=ResolutionType.REFUND_ISSUED,
            issues_resolved=[IssueType.WRONG_ITEM_RECEIVED],
            policy_violations=[], timeout_flag=False, escalated=False,
        )
        d.update(kw)
        return TicketState(**d)

    grader = Grader()
    cases = [
        (_state(), _cfg()),
        (_state(timeout_flag=True), _cfg()),
        (_state(resolution=ResolutionType.ESCALATED), _cfg()),
        (_state(step_count=8, customer_sentiment=0.2), _cfg()),
        (
            _state(resolution=ResolutionType.PARTIAL_REFUND_ISSUED, policy_violations=["POL-FRAUD-001"]),
            _cfg(applicable_policy_ids=["POL-FRAUD-001", "POL-REFUND-001"]),
        ),
    ]
    for i, (st, cfg) in enumerate(cases, 1):
        reward, _ = grader.score(st, cfg)
        assert isinstance(reward, float), f"Case {i}: reward not float ({type(reward)})"
        assert 0.0 <= reward <= 1.0, f"Case {i}: reward out of range ({reward})"


# ---------------------------------------------------------------------------
# CHECK 6: Full episode runs end-to-end in memory (no server required)
# ---------------------------------------------------------------------------
async def check_6() -> None:
    import tempfile

    from models import SupportAction, ActionType, PolicyRule, KBArticle
    from server.ticket_generator import TicketGenerator
    from server.tool_router import ToolRouter
    from server.grader import Grader
    from server.environment import SupportEnvironment

    _DATA = _ROOT / "data"

    def _load_policies(path: Path) -> dict:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("policies", raw) if isinstance(raw, dict) else raw
        return {p["policy_id"]: PolicyRule(**p) for p in items}

    def _load_kb(path: Path) -> list:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("articles", raw) if isinstance(raw, dict) else raw
        return [KBArticle(**a) for a in items]

    with tempfile.TemporaryDirectory() as tmp:
        episodes_dir = Path(tmp) / "episodes"
        gen = TicketGenerator(_DATA / "tickets.json")
        env = SupportEnvironment(
            ticket_generator=gen,
            tool_router=ToolRouter(
                policies=_load_policies(_DATA / "policies.json"),
                kb_articles=_load_kb(_DATA / "knowledge_base.json"),
            ),
            grader=Grader(),
            episodes_dir=episodes_dir,
        )

        obs = await env.reset("easy_refund")
        ep = obs.episode_id

        cfg = gen.get_config("easy_refund")
        order_id = cfg.order_ids[0]
        amount = cfg.db_seed.orders[0].total_amount

        def _act(action_type, **params):
            return SupportAction(action_type=action_type, parameters=params)

        await env.step(_act(ActionType.LOOKUP_ORDER, order_id=order_id), ep)
        await env.step(_act(ActionType.CHECK_POLICY, policy_id="POL-REFUND-001"), ep)
        await env.step(
            _act(ActionType.ISSUE_REFUND, order_id=order_id, amount=amount,
                 refund_type="full", reason="Wrong item"),
            ep,
        )
        result = await env.step(
            _act(ActionType.CLOSE_TICKET, resolution="refund_issued",
                 summary="Full refund issued for wrong item."),
            ep,
        )

    assert result.done is True, f"Expected done=True, got {result.done}"
    assert result.reward > 0.0, f"Expected reward > 0.0, got {result.reward}"


# ---------------------------------------------------------------------------
# CHECK 7: client.py imports cleanly
# ---------------------------------------------------------------------------
def check_7() -> None:
    from client import SupportEnv, make_action  # noqa: F401
    assert callable(make_action)


# ---------------------------------------------------------------------------
# CHECK 8: baseline.py is importable (do not execute it — needs a server)
# ---------------------------------------------------------------------------
def check_8() -> None:
    baseline = importlib.import_module("baseline")
    assert baseline is not None


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------
def main() -> int:
    checks = [
        (1, "Models import cleanly", check_1),
        (2, "Data files are valid JSON with correct structure", check_2),
        (3, "TicketGenerator loads all required task configs", check_3),
        (4, "Grader produces 0.975 for perfect easy_refund", check_4),
        (5, "Reward is always float in [0.0, 1.0] across 5 cases", check_5),
        (6, "Full episode runs end-to-end in memory", check_6),
        (7, "client.py imports cleanly", check_7),
        (8, "baseline.py is importable", check_8),
    ]

    print(f"\n{_BOLD}Customer Support Resolution Gym — Pre-Submission Verification{_RESET}")
    print("=" * 64)

    for num, label, fn in checks:
        print(f"\nCHECK {num}: {label}")
        _run(num, label, fn)

    passed = sum(1 for v in _results.values() if v)
    total = len(checks)
    failed = [num for num, ok in _results.items() if not ok]

    print("\n" + "=" * 64)
    print(f"{_BOLD}CHECKS PASSED: {passed}/{total}{_RESET}")

    if passed == total:
        print(f"{_GREEN}{_BOLD}✓  READY TO SUBMIT{_RESET}")
    else:
        print(f"{_RED}{_BOLD}✗  FIX BEFORE SUBMITTING{_RESET}")
        print(f"   Failed checks: {', '.join(f'CHECK {n}' for n in sorted(failed))}")

    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
