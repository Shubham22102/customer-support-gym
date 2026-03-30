from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field, model_validator

from openenv.core.models import Action, Observation


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    LOOKUP_ORDER = "lookup_order"
    CHECK_POLICY = "check_policy"
    SEARCH_KB = "search_kb"
    REQUEST_INFO = "request_info"
    ISSUE_REFUND = "issue_refund"
    SEND_MESSAGE = "send_message"
    ESCALATE = "escalate"
    CLOSE_TICKET = "close_ticket"


class ResolutionType(str, Enum):
    REFUND_ISSUED = "refund_issued"
    PARTIAL_REFUND_ISSUED = "partial_refund_issued"
    REPLACEMENT_SHIPPED = "replacement_shipped"
    ESCALATED = "escalated"
    ACCOUNT_UNLOCKED = "account_unlocked"
    INFORMATION_PROVIDED = "information_provided"
    NO_ACTION_REQUIRED = "no_action_required"
    COMPENSATION_ISSUED = "compensation_issued"
    MULTIPLE_RESOLUTIONS = "multiple_resolutions"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ESCALATED = "escalated"
    CLOSED = "closed"


class IssueCategory(str, Enum):
    SHIPPING = "shipping"
    BILLING = "billing"
    ACCOUNT = "account"
    PRODUCT = "product"


class IssueType(str, Enum):
    LATE_DELIVERY = "late_delivery"
    WRONG_ADDRESS = "wrong_address"
    LOST_IN_TRANSIT = "lost_in_transit"
    DAMAGED_ITEM = "damaged_item"
    TRACKING_STALE = "tracking_stale"
    DUPLICATE_CHARGE = "duplicate_charge"
    WRONG_AMOUNT = "wrong_amount"
    SUBSCRIPTION_CONFUSION = "subscription_confusion"
    REFUND_NOT_RECEIVED = "refund_not_received"
    PROMO_NOT_APPLIED = "promo_not_applied"
    ACCOUNT_LOCKED = "account_locked"
    EMAIL_CHANGE = "email_change"
    PASSWORD_RESET_LOOP = "password_reset_loop"
    TWO_FA_BROKEN = "two_fa_broken"
    DATA_DELETION = "data_deletion"
    WRONG_ITEM_RECEIVED = "wrong_item_received"
    DEFECTIVE_ITEM = "defective_item"
    MISSING_PARTS = "missing_parts"
    WRONG_SIZE = "wrong_size"
    QUALITY_COMPLAINT = "quality_complaint"
    UNAUTHORIZED_TRANSACTION = "unauthorized_transaction"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    RETURNED = "returned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    LOST_IN_TRANSIT = "lost_in_transit"


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    PAYPAL = "paypal"
    SHOP_CREDIT = "shop_credit"


class LoyaltyTier(str, Enum):
    STANDARD = "standard"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class EscalationReason(str, Enum):
    POTENTIAL_FRAUD = "potential_fraud"
    LEGAL_THREAT = "legal_threat"
    HIGH_VALUE_REFUND = "high_value_refund"
    ACCOUNT_SECURITY = "account_security"
    TECHNICAL_ISSUE = "technical_issue"
    MANAGER_REVIEW = "manager_review"
    POLICY_EXCEPTION = "policy_exception"


class EscalationTeam(str, Enum):
    FRAUD_INVESTIGATION = "fraud_investigation"
    MANAGER = "manager"
    LEGAL = "legal"
    TECHNICAL = "technical"
    BILLING_SPECIALIST = "billing_specialist"


class InfoType(str, Enum):
    ORDER_ID = "order_id"
    TRANSACTION_ID = "transaction_id"
    PHOTO_EVIDENCE = "photo_evidence"
    ACCOUNT_DETAILS = "account_details"
    OTHER = "other"


class MessageType(str, Enum):
    APOLOGY = "apology"
    UPDATE = "update"
    EXPLANATION = "explanation"
    CONFIRMATION = "confirmation"
    CLOSING = "closing"


class TaskDifficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    APPAREL = "apparel"
    HOME_GOODS = "home_goods"


class RefundType(str, Enum):
    FULL = "full"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class SupportAction(Action):
    """An action taken by the support agent."""

    action_type: ActionType = Field(
        ...,
        description="The type of action the agent is taking in this step.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value parameters required to execute the action (e.g. order_id, query string).",
    )


class SupportObservation(Observation):
    """The observation returned to the agent after each environment step."""

    customer_message: str = Field(
        ...,
        description="The latest message from the customer in the support conversation.",
    )
    tool_result: dict[str, Any] | None = Field(
        default=None,
        description="Structured result returned by the last tool call, or None if no tool was called.",
    )
    ticket_status: TicketStatus = Field(
        default=TicketStatus.OPEN,
        description="Current status of the support ticket.",
    )
    step_count: int = Field(
        default=0,
        ge=0,
        description="Number of steps taken in the current episode so far.",
    )
    max_steps: int = Field(
        ...,
        gt=0,
        description="Maximum number of steps allowed for this episode.",
    )
    sentiment_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Estimated customer sentiment score between 0.0 (very negative) and 1.0 (very positive).",
    )
    available_actions: list[str] = Field(
        default_factory=list,
        description="List of action type strings currently available to the agent.",
    )
    issues_identified: list[str] = Field(
        default_factory=list,
        description="List of issue type strings identified so far in this episode.",
    )
    timeout_flag: bool = Field(
        default=False,
        description="True if the episode has exceeded the maximum allowed steps.",
    )
    episode_id: str = Field(
        ...,
        description="Unique identifier for the current episode.",
    )
    task_id: str = Field(
        ...,
        description="Identifier of the task configuration driving this episode.",
    )


class TicketState(BaseModel):
    """Internal mutable state for a single support ticket episode."""

    episode_id: str = Field(
        ...,
        description="Unique identifier for the episode this ticket belongs to.",
    )
    task_id: str = Field(
        ...,
        description="Identifier of the task configuration for this episode.",
    )
    ticket_id: str = Field(
        ...,
        description="Unique identifier for the support ticket.",
    )
    ticket_status: TicketStatus = Field(
        default=TicketStatus.OPEN,
        description="Current status of the ticket.",
    )
    step_count: int = Field(
        default=0,
        description="Number of agent steps completed in this episode.",
    )
    max_steps: int = Field(
        default=8,
        description="Maximum steps allowed before the episode times out.",
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the episode was started.",
    )
    customer_id: str = Field(
        default="",
        description="Identifier of the customer associated with this ticket.",
    )
    customer_sentiment: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Current estimated sentiment of the customer (0.0 = very negative, 1.0 = very positive).",
    )
    resolution: ResolutionType | None = Field(
        default=None,
        description="The resolution type applied when the ticket is closed, or None if still open.",
    )
    resolution_summary: str = Field(
        default="",
        description="Human-readable summary of how the ticket was resolved.",
    )
    issues_identified: list[IssueType] = Field(
        default_factory=list,
        description="List of issue types identified during this episode.",
    )
    issues_resolved: list[IssueType] = Field(
        default_factory=list,
        description="List of issue types that have been fully resolved.",
    )
    actions_taken: list[ActionType] = Field(
        default_factory=list,
        description="Ordered list of action types the agent has executed in this episode.",
    )
    messages_sent: list[str] = Field(
        default_factory=list,
        description="List of message bodies sent to the customer during this episode.",
    )
    refund_issued: bool = Field(
        default=False,
        description="True if a refund has been issued in this episode.",
    )
    refund_amount: float = Field(
        default=0.0,
        description="Total refund amount issued in this episode (in dollars).",
    )
    refund_order_id: str = Field(
        default="",
        description="Order ID against which the refund was issued.",
    )
    escalated: bool = Field(
        default=False,
        description="True if the ticket has been escalated to another team.",
    )
    escalation_team: EscalationTeam | None = Field(
        default=None,
        description="The team the ticket was escalated to, or None if not escalated.",
    )
    escalation_reason: EscalationReason | None = Field(
        default=None,
        description="The reason the ticket was escalated, or None if not escalated.",
    )
    policy_violations: list[str] = Field(
        default_factory=list,
        description="List of policy IDs or descriptions that the agent violated.",
    )
    policies_checked: list[str] = Field(
        default_factory=list,
        description="List of policy IDs that were consulted during this episode.",
    )
    info_requested: bool = Field(
        default=False,
        description="True if the agent requested additional information from the customer.",
    )
    info_type_requested: InfoType | None = Field(
        default=None,
        description="The type of additional information requested, or None if not requested.",
    )
    timeout_flag: bool = Field(
        default=False,
        description="True if the episode ended due to exceeding max_steps.",
    )
    fraud_flag: bool = Field(
        default=False,
        description="True if a potential fraud signal was detected during this episode.",
    )


class ShippingAddress(BaseModel):
    """A physical shipping address."""

    street: str = Field(
        ...,
        description="Street address line (e.g. '123 Main St').",
    )
    city: str = Field(
        ...,
        description="City name.",
    )
    state: str = Field(
        ...,
        description="State or province code (e.g. 'CA').",
    )
    zip: str = Field(
        ...,
        description="Postal/ZIP code.",
    )
    country: str = Field(
        default="US",
        description="ISO 3166-1 alpha-2 country code.",
    )


class OrderItem(BaseModel):
    """A single line item within an order."""

    sku: str = Field(
        ...,
        description="Stock-keeping unit identifier for the product.",
    )
    name: str = Field(
        ...,
        description="Human-readable name of the product.",
    )
    quantity: int = Field(
        ...,
        ge=1,
        description="Number of units ordered (minimum 1).",
    )
    unit_price: float = Field(
        ...,
        gt=0.0,
        description="Price per unit in dollars (must be greater than 0).",
    )

    @property
    def subtotal(self) -> float:
        """Computed line-item subtotal rounded to 2 decimal places."""
        return round(self.quantity * self.unit_price, 2)


class ProductRecord(BaseModel):
    """A product record from the product catalog."""

    sku: str = Field(
        ...,
        description="Unique stock-keeping unit identifier.",
    )
    name: str = Field(
        ...,
        description="Human-readable product name.",
    )
    category: ProductCategory = Field(
        ...,
        description="High-level product category.",
    )
    price: float = Field(
        ...,
        description="Current retail price in dollars.",
    )
    weight_kg: float = Field(
        ...,
        description="Product weight in kilograms.",
    )


class OrderRecord(BaseModel):
    """A complete order record from the order management system."""

    order_id: str = Field(
        ...,
        description="Unique order identifier.",
    )
    customer_id: str = Field(
        ...,
        description="Identifier of the customer who placed the order.",
    )
    items: list[OrderItem] = Field(
        ...,
        description="List of line items included in the order.",
    )
    status: OrderStatus = Field(
        ...,
        description="Current fulfillment status of the order.",
    )
    total_amount: float = Field(
        ...,
        description="Total charged amount for the order in dollars.",
    )
    payment_method: PaymentMethod = Field(
        ...,
        description="Payment method used for this order.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp string when the order was placed.",
    )
    shipped_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp string when the order was shipped, or None.",
    )
    delivered_at: str | None = Field(
        default=None,
        description="ISO 8601 timestamp string when the order was delivered, or None.",
    )
    tracking_number: str | None = Field(
        default=None,
        description="Carrier tracking number for the shipment, or None if not yet shipped.",
    )
    shipping_address: ShippingAddress = Field(
        ...,
        description="Destination address for the shipment.",
    )
    fraud_flagged: bool = Field(
        default=False,
        description="True if this order has been flagged for potential fraud.",
    )

    @property
    def days_since_delivery(self) -> int | None:
        """Number of whole days elapsed since delivery, or None if not yet delivered."""
        if self.delivered_at is None:
            return None
        delivered_dt = datetime.fromisoformat(self.delivered_at)
        delta = datetime.utcnow() - delivered_dt
        return delta.days


class CustomerRecord(BaseModel):
    """A customer account record."""

    customer_id: str = Field(
        ...,
        description="Unique customer identifier.",
    )
    name: str = Field(
        ...,
        description="Customer's full name.",
    )
    email: str = Field(
        ...,
        description="Customer's primary email address.",
    )
    account_status: AccountStatus = Field(
        ...,
        description="Current status of the customer's account.",
    )
    loyalty_tier: LoyaltyTier = Field(
        ...,
        description="Customer's loyalty programme tier.",
    )
    order_history: list[str] = Field(
        ...,
        description="List of order IDs placed by this customer.",
    )
    total_lifetime_spend: float = Field(
        ...,
        ge=0.0,
        description="Cumulative spend by this customer in dollars (non-negative).",
    )
    open_disputes: int = Field(
        ...,
        ge=0,
        description="Number of currently open disputes for this customer (non-negative).",
    )


class PolicyRule(BaseModel):
    """A single support policy rule."""

    policy_id: str = Field(
        ...,
        description="Unique identifier for this policy rule.",
    )
    category: str = Field(
        ...,
        description="Category of the policy (e.g. 'refunds', 'shipping').",
    )
    rule_description: str = Field(
        ...,
        description="Human-readable description of the policy rule.",
    )
    conditions: list[str] = Field(
        ...,
        description="List of conditions under which this policy applies.",
    )
    required_action: str | None = Field(
        default=None,
        description="Action that must be taken if the policy applies, or None.",
    )
    forbidden_actions: list[str] = Field(
        ...,
        description="List of actions that are prohibited under this policy.",
    )


class KBArticle(BaseModel):
    """A knowledge-base article for agent reference."""

    article_id: str = Field(
        ...,
        description="Unique identifier for the knowledge-base article.",
    )
    title: str = Field(
        ...,
        description="Title of the knowledge-base article.",
    )
    category: str = Field(
        ...,
        description="Category this article belongs to.",
    )
    content: str = Field(
        ...,
        description="Full text content of the article.",
    )
    related_policy_ids: list[str] = Field(
        ...,
        description="List of policy IDs that are referenced by this article.",
    )


class RefundRecord(BaseModel):
    """A record of a refund transaction."""

    refund_id: str = Field(
        ...,
        description="Unique identifier for this refund.",
    )
    order_id: str = Field(
        ...,
        description="Order ID against which this refund was issued.",
    )
    customer_id: str = Field(
        ...,
        description="Identifier of the customer receiving the refund.",
    )
    amount: float = Field(
        ...,
        description="Refund amount in dollars.",
    )
    refund_type: RefundType = Field(
        ...,
        description="Whether this is a full or partial refund.",
    )
    reason: str = Field(
        ...,
        description="Human-readable reason for issuing the refund.",
    )
    status: str = Field(
        default="processed",
        description="Processing status of the refund (e.g. 'processed', 'pending').",
    )
    eta_days: int = Field(
        default=5,
        description="Estimated number of business days until the refund reaches the customer.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp string when the refund was created.",
    )


class EscalationRecord(BaseModel):
    """A record of a ticket escalation."""

    escalation_id: str = Field(
        ...,
        description="Unique identifier for this escalation event.",
    )
    ticket_id: str = Field(
        ...,
        description="Identifier of the ticket that was escalated.",
    )
    reason: EscalationReason = Field(
        ...,
        description="Reason the ticket was escalated.",
    )
    team: EscalationTeam = Field(
        ...,
        description="Team to which the ticket was escalated.",
    )
    notes: str = Field(
        ...,
        description="Additional context or notes provided at escalation time.",
    )
    status: str = Field(
        default="submitted",
        description="Current status of the escalation (e.g. 'submitted', 'in_review').",
    )
    eta_hours: int = Field(
        default=24,
        description="Estimated hours until the escalation team responds.",
    )
    created_at: str = Field(
        ...,
        description="ISO 8601 timestamp string when the escalation was created.",
    )


class DBSeed(BaseModel):
    """Seed data bundle used to populate the in-memory database for an episode."""

    customers: list[CustomerRecord] = Field(
        ...,
        description="List of customer records to seed.",
    )
    orders: list[OrderRecord] = Field(
        ...,
        description="List of order records to seed.",
    )
    products: list[ProductRecord] = Field(
        ...,
        description="List of product records to seed.",
    )


class EpisodeConfig(BaseModel):
    """Full configuration for a single gym episode / task."""

    ticket_id: str = Field(
        ...,
        description="Unique identifier for the support ticket this episode simulates.",
    )
    task_id: str = Field(
        ...,
        description="Identifier of the task definition driving this episode.",
    )
    difficulty: TaskDifficulty = Field(
        ...,
        description="Difficulty level of this task.",
    )
    max_steps: int = Field(
        ...,
        description="Maximum number of agent steps allowed for this episode.",
    )
    optimal_steps: int = Field(
        ...,
        description="Number of steps an optimal policy would use to resolve this episode.",
    )
    category: IssueCategory = Field(
        ...,
        description="High-level issue category for this episode.",
    )
    issue_types: list[IssueType] = Field(
        ...,
        description="All specific issue types present in this episode.",
    )
    opening_message: str = Field(
        ...,
        description="The initial customer message that begins the conversation.",
    )
    ground_truth_resolution: ResolutionType = Field(
        ...,
        description="The correct resolution type for a perfectly handled episode.",
    )
    applicable_policy_ids: list[str] = Field(
        ...,
        description="List of policy IDs that apply to and should be consulted for this episode.",
    )
    customer_id: str = Field(
        ...,
        description="Identifier of the customer involved in this episode.",
    )
    order_ids: list[str] = Field(
        ...,
        description="List of order IDs relevant to this episode.",
    )
    fraud_flag: bool = Field(
        default=False,
        description="True if this episode contains a fraud scenario.",
    )
    customer_replies: dict[str, str] = Field(
        ...,
        description="Mapping of action-key strings to scripted customer reply messages.",
    )
    trap_actions: list[str] = Field(
        ...,
        description="List of action type strings that constitute traps or penalised actions in this episode.",
    )
    db_seed: DBSeed = Field(
        ...,
        description="Seed data bundle containing all records needed for this episode.",
    )
