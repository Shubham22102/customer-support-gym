from __future__ import annotations

import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import aiosqlite
from openenv.core.environment import Environment
from openenv.core.models import StepResult

from models import (
    SupportAction,
    SupportObservation,
    TicketState,
    EpisodeConfig,
    TicketStatus,
    ActionType,
    ResolutionType,
    IssueType,
)
from server.ticket_generator import TicketGenerator
from server.tool_router import ToolRouter
from server.grader import Grader


# ---------------------------------------------------------------------------
# Module-level SQL for schema creation
# ---------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
    price REAL NOT NULL, weight_kg REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
    account_status TEXT NOT NULL, loyalty_tier TEXT NOT NULL,
    total_lifetime_spend REAL NOT NULL DEFAULT 0.0, open_disputes INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, status TEXT NOT NULL,
    total_amount REAL NOT NULL, payment_method TEXT NOT NULL,
    created_at TEXT NOT NULL, shipped_at TEXT, delivered_at TEXT,
    tracking_number TEXT, fraud_flagged INTEGER NOT NULL DEFAULT 0,
    street TEXT NOT NULL, city TEXT NOT NULL, state TEXT NOT NULL,
    zip TEXT NOT NULL, country TEXT NOT NULL DEFAULT 'US'
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
    sku TEXT NOT NULL, name TEXT NOT NULL,
    quantity INTEGER NOT NULL, unit_price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS refunds (
    refund_id TEXT PRIMARY KEY, order_id TEXT NOT NULL, customer_id TEXT NOT NULL,
    amount REAL NOT NULL, refund_type TEXT NOT NULL, reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processed', eta_days INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS escalations (
    escalation_id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL,
    reason TEXT NOT NULL, team TEXT NOT NULL, notes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted', eta_hours INTEGER NOT NULL DEFAULT 24,
    created_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# SupportEnvironment
# ---------------------------------------------------------------------------


class SupportEnvironment(Environment):
    """Orchestrator environment for the Customer Support Resolution Gym."""

    def __init__(
        self,
        ticket_generator: TicketGenerator,
        tool_router: ToolRouter,
        grader: Grader,
        episodes_dir: Path = Path("data/episodes"),
    ) -> None:
        self._ticket_generator = ticket_generator
        self._tool_router = tool_router
        self._grader = grader
        self._episodes: dict[str, tuple[TicketState, EpisodeConfig]] = {}
        self._episodes_dir = episodes_dir
        episodes_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # reset
    # ------------------------------------------------------------------

    async def reset(self, task_id: str = "easy_refund") -> SupportObservation:
        config: EpisodeConfig = self._ticket_generator.get_config(task_id)

        episode_id = str(uuid.uuid4())
        db_path = self._episodes_dir / f"{episode_id}.db"

        await self._seed_database(db_path, config)

        state = TicketState(
            episode_id=episode_id,
            task_id=task_id,
            ticket_id=config.ticket_id,
            max_steps=config.max_steps,
            customer_id=config.customer_id,
        )
        state.fraud_flag = config.fraud_flag

        self._episodes[episode_id] = (state, config)

        return SupportObservation(
            customer_message=config.opening_message,
            tool_result=None,
            ticket_status=TicketStatus.OPEN,
            step_count=0,
            max_steps=config.max_steps,
            sentiment_score=0.5,
            available_actions=[a.value for a in ActionType],
            issues_identified=[],
            timeout_flag=False,
            episode_id=episode_id,
            task_id=task_id,
        )

    # ------------------------------------------------------------------
    # _seed_database
    # ------------------------------------------------------------------

    async def _seed_database(self, db_path: Path, config: EpisodeConfig) -> None:
        async with aiosqlite.connect(db_path) as db:
            await db.executescript(_CREATE_TABLES_SQL)

            # Seed products
            for product in config.db_seed.products:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO products (sku, name, category, price, weight_kg)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        product.sku,
                        product.name,
                        product.category.value,
                        product.price,
                        product.weight_kg,
                    ),
                )

            # Seed customers
            for customer in config.db_seed.customers:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO customers
                        (customer_id, name, email, account_status, loyalty_tier,
                         total_lifetime_spend, open_disputes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        customer.customer_id,
                        customer.name,
                        customer.email,
                        customer.account_status.value,
                        customer.loyalty_tier.value,
                        customer.total_lifetime_spend,
                        customer.open_disputes,
                    ),
                )

            # Seed orders and their items
            for order in config.db_seed.orders:
                addr = order.shipping_address
                await db.execute(
                    """
                    INSERT OR REPLACE INTO orders
                        (order_id, customer_id, status, total_amount, payment_method,
                         created_at, shipped_at, delivered_at, tracking_number,
                         fraud_flagged, street, city, state, zip, country)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.order_id,
                        order.customer_id,
                        order.status.value,
                        order.total_amount,
                        order.payment_method.value,
                        order.created_at,
                        order.shipped_at,
                        order.delivered_at,
                        order.tracking_number,
                        int(order.fraud_flagged),
                        addr.street,
                        addr.city,
                        addr.state,
                        addr.zip,
                        addr.country,
                    ),
                )
                for item in order.items:
                    await db.execute(
                        """
                        INSERT INTO order_items (order_id, sku, name, quantity, unit_price)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            order.order_id,
                            item.sku,
                            item.name,
                            item.quantity,
                            item.unit_price,
                        ),
                    )

            await db.commit()

    # ------------------------------------------------------------------
    # step
    # ------------------------------------------------------------------

    async def step(self, action: SupportAction, episode_id: str) -> StepResult:
        state, config = self._episodes[episode_id]
        db_path = self._episodes_dir / f"{episode_id}.db"

        async with aiosqlite.connect(db_path) as db:
            tool_result = await self._tool_router.execute(action, state, db, config)

        # Apply state mutations
        for key, value in tool_result.state_mutations.items():
            setattr(state, key, value)

        # Apply sentiment delta (clamped to [0.0, 1.0])
        state.customer_sentiment = max(
            0.0, min(1.0, state.customer_sentiment + tool_result.sentiment_delta)
        )

        # Advance step counter and record action
        state.step_count += 1
        state.actions_taken.append(action.action_type)

        # Determine episode completion
        done = (action.action_type == ActionType.CLOSE_TICKET) or (
            state.step_count >= config.max_steps
        )

        if state.step_count >= config.max_steps and action.action_type != ActionType.CLOSE_TICKET:
            state.timeout_flag = True

        reward = 0.0
        info: dict[str, Any] = {}

        if done:
            reward, info = self._grader.score(state, config)

            # Clean up episode DB
            db_path_cleanup = self._episodes_dir / f"{episode_id}.db"
            try:
                db_path_cleanup.unlink()
            except Exception:
                pass

            del self._episodes[episode_id]

        # Compute available actions for the observation
        available_actions = [a.value for a in ActionType]
        if action.action_type == ActionType.CLOSE_TICKET:
            # Ticket already closed — no further actions meaningful
            available_actions = []

        observation = SupportObservation(
            customer_message=getattr(state, "customer_message", config.opening_message),
            tool_result=tool_result.tool_result,
            ticket_status=state.ticket_status,
            step_count=state.step_count,
            max_steps=config.max_steps,
            sentiment_score=state.customer_sentiment,
            available_actions=available_actions,
            issues_identified=[i.value for i in state.issues_identified],
            timeout_flag=state.timeout_flag,
            episode_id=episode_id,
            task_id=state.task_id,
        )

        return StepResult(observation=observation, reward=reward, done=done, info=info)

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------

    async def state(self, episode_id: str) -> dict[str, Any]:
        entry = self._episodes.get(episode_id)
        if entry is None:
            return {"error": "Episode not found"}

        state, _ = entry

        raw = state.model_dump()

        # Ensure JSON serialisability: convert enums/datetimes to primitives
        def _serialise(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if hasattr(obj, "value"):
                return obj.value
            if isinstance(obj, list):
                return [_serialise(v) for v in obj]
            if isinstance(obj, dict):
                return {k: _serialise(v) for k, v in obj.items()}
            return obj

        return {k: _serialise(v) for k, v in raw.items()}
