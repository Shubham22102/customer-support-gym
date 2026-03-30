# DATA_SCHEMA.md — Customer Support Resolution Gym
## Complete Data Model Specification

**Version:** 1.0.0
**Authority:** This document is the single source of truth for all data types.
**Rule:** An AI coding agent must copy every model, enum, and field from this document
exactly as written. Do not rename fields. Do not add fields. Do not change types.
Do not define any model outside of `models.py`.

---

## Table of Contents

1. [Enumerations](#1-enumerations)
2. [Pydantic Models — API Layer](#2-pydantic-models--api-layer)
3. [Pydantic Models — Internal State](#3-pydantic-models--internal-state)
4. [Pydantic Models — Data Records](#4-pydantic-models--data-records)
5. [JSON Schema — tickets.json](#5-json-schema--ticketsjson)
6. [JSON Schema — policies.json](#6-json-schema--policiesjson)
7. [JSON Schema — knowledge_base.json](#7-json-schema--knowledge_basejson)
8. [SQLite Schema](#8-sqlite-schema)
9. [Field Contracts and Invariants](#9-field-contracts-and-invariants)
10. [Import Map](#10-import-map)

---

## 1. Enumerations

All enums live in `models.py`. All enums inherit from `str, Enum` so they
serialize to their string value in JSON automatically.

### 1.1 `ActionType`

Maps to the 8 valid agent actions. No other values exist.

```python
class ActionType(str, Enum):
    LOOKUP_ORDER  = "lookup_order"
    CHECK_POLICY  = "check_policy"
    SEARCH_KB     = "search_kb"
    REQUEST_INFO  = "request_info"
    ISSUE_REFUND  = "issue_refund"
    SEND_MESSAGE  = "send_message"
    ESCALATE      = "escalate"
    CLOSE_TICKET  = "close_ticket"
```

### 1.2 `ResolutionType`

The set of valid resolutions an agent can pass to `close_ticket`. The grader
compares the agent's choice against the `ground_truth_resolution` in the ticket
config.

```python
class ResolutionType(str, Enum):
    REFUND_ISSUED          = "refund_issued"
    PARTIAL_REFUND_ISSUED  = "partial_refund_issued"
    REPLACEMENT_SHIPPED    = "replacement_shipped"
    ESCALATED              = "escalated"
    ACCOUNT_UNLOCKED       = "account_unlocked"
    INFORMATION_PROVIDED   = "information_provided"
    NO_ACTION_REQUIRED     = "no_action_required"
    COMPENSATION_ISSUED    = "compensation_issued"
    MULTIPLE_RESOLUTIONS   = "multiple_resolutions"
```

### 1.3 `TicketStatus`

Tracks the lifecycle state of a ticket within an episode.

```python
class TicketStatus(str, Enum):
    OPEN         = "open"
    IN_PROGRESS  = "in_progress"
    ESCALATED    = "escalated"
    CLOSED       = "closed"
```

### 1.4 `IssueCategory`

Top-level category of the customer's complaint. Each ticket has exactly one
primary category.

```python
class IssueCategory(str, Enum):
    SHIPPING  = "shipping"
    BILLING   = "billing"
    ACCOUNT   = "account"
    PRODUCT   = "product"
```

### 1.5 `IssueType`

Specific issue within a category. A ticket may surface one or more issue types.
This list is exhaustive for v1.0.

```python
class IssueType(str, Enum):
    # Shipping
    LATE_DELIVERY       = "late_delivery"
    WRONG_ADDRESS       = "wrong_address"
    LOST_IN_TRANSIT     = "lost_in_transit"
    DAMAGED_ITEM        = "damaged_item"
    TRACKING_STALE      = "tracking_stale"
    # Billing
    DUPLICATE_CHARGE    = "duplicate_charge"
    WRONG_AMOUNT        = "wrong_amount"
    SUBSCRIPTION_CONFUSION = "subscription_confusion"
    REFUND_NOT_RECEIVED = "refund_not_received"
    PROMO_NOT_APPLIED   = "promo_not_applied"
    # Account
    ACCOUNT_LOCKED      = "account_locked"
    EMAIL_CHANGE        = "email_change"
    PASSWORD_RESET_LOOP = "password_reset_loop"
    TWO_FA_BROKEN       = "two_fa_broken"
    DATA_DELETION       = "data_deletion"
    # Product
    WRONG_ITEM_RECEIVED = "wrong_item_received"
    DEFECTIVE_ITEM      = "defective_item"
    MISSING_PARTS       = "missing_parts"
    WRONG_SIZE          = "wrong_size"
    QUALITY_COMPLAINT   = "quality_complaint"
    # Cross-category (used in multi_issue task only)
    UNAUTHORIZED_TRANSACTION = "unauthorized_transaction"
```

### 1.6 `OrderStatus`

```python
class OrderStatus(str, Enum):
    PENDING           = "pending"
    SHIPPED           = "shipped"
    DELIVERED         = "delivered"
    RETURNED          = "returned"
    COMPLETED         = "completed"
    CANCELLED         = "cancelled"
    LOST_IN_TRANSIT   = "lost_in_transit"
```

### 1.7 `PaymentMethod`

```python
class PaymentMethod(str, Enum):
    CREDIT_CARD   = "credit_card"
    DEBIT_CARD    = "debit_card"
    PAYPAL        = "paypal"
    SHOP_CREDIT   = "shop_credit"
```

### 1.8 `LoyaltyTier`

```python
class LoyaltyTier(str, Enum):
    STANDARD  = "standard"
    SILVER    = "silver"
    GOLD      = "gold"
    PLATINUM  = "platinum"
```

### 1.9 `AccountStatus`

```python
class AccountStatus(str, Enum):
    ACTIVE                = "active"
    LOCKED                = "locked"
    SUSPENDED             = "suspended"
    PENDING_VERIFICATION  = "pending_verification"
```

### 1.10 `EscalationReason`

```python
class EscalationReason(str, Enum):
    POTENTIAL_FRAUD    = "potential_fraud"
    LEGAL_THREAT       = "legal_threat"
    HIGH_VALUE_REFUND  = "high_value_refund"
    ACCOUNT_SECURITY   = "account_security"
    TECHNICAL_ISSUE    = "technical_issue"
    MANAGER_REVIEW     = "manager_review"
    POLICY_EXCEPTION   = "policy_exception"
```

### 1.11 `EscalationTeam`

```python
class EscalationTeam(str, Enum):
    FRAUD_INVESTIGATION  = "fraud_investigation"
    MANAGER              = "manager"
    LEGAL                = "legal"
    TECHNICAL            = "technical"
    BILLING_SPECIALIST   = "billing_specialist"
```

### 1.12 `InfoType`

Used by the `request_info` action to categorise what the agent is asking for.

```python
class InfoType(str, Enum):
    ORDER_ID         = "order_id"
    TRANSACTION_ID   = "transaction_id"
    PHOTO_EVIDENCE   = "photo_evidence"
    ACCOUNT_DETAILS  = "account_details"
    OTHER            = "other"
```

### 1.13 `MessageType`

Used by the `send_message` action.

```python
class MessageType(str, Enum):
    APOLOGY       = "apology"
    UPDATE        = "update"
    EXPLANATION   = "explanation"
    CONFIRMATION  = "confirmation"
    CLOSING       = "closing"
```

### 1.14 `TaskDifficulty`

```python
class TaskDifficulty(str, Enum):
    EASY    = "easy"
    MEDIUM  = "medium"
    HARD    = "hard"
```

### 1.15 `ProductCategory`

```python
class ProductCategory(str, Enum):
    ELECTRONICS  = "electronics"
    APPAREL      = "apparel"
    HOME_GOODS   = "home_goods"
```

### 1.16 `RefundType`

```python
class RefundType(str, Enum):
    FULL     = "full"
    PARTIAL  = "partial"
```

---

## 2. Pydantic Models — API Layer

These are the models that cross the OpenEnv client–server boundary. They must
inherit from the OpenEnv base classes.

### 2.1 `SupportAction`

```python
from openenv.core.models import Action
from pydantic import Field
from typing import Any

class SupportAction(Action):
    """
    The action submitted by the agent at each step.
    `parameters` shape varies by action_type — see PRD.md Section 5.
    """
    action_type: ActionType = Field(
        ...,
        description="One of the 8 valid ActionType enum values.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Action-specific parameters. Shape must match the schema defined "
            "in PRD.md for the given action_type. Extra keys are ignored."
        ),
    )
```

**Parameter schemas per `action_type` — enforced in `tool_router.py`:**

```python
# lookup_order
{"order_id": str}                                        # required

# check_policy
{"policy_id": str}                                       # required

# search_kb
{"query": str}                                           # required, 5–200 chars

# request_info
{"message": str, "info_type": InfoType}                  # both required; message 10–500 chars

# issue_refund
{"order_id": str, "amount": float,                       # all required
 "reason": str, "refund_type": RefundType}               # reason max 200 chars

# send_message
{"message": str, "message_type": MessageType}            # both required; message 10–1000 chars

# escalate
{"reason": EscalationReason,                             # all required
 "team": EscalationTeam,
 "notes": str}                                           # notes 20–500 chars

# close_ticket
{"resolution": ResolutionType, "summary": str}           # both required; summary 20–500 chars
```

---

### 2.2 `SupportObservation`

```python
from openenv.core.models import Observation
from pydantic import Field

class SupportObservation(Observation):
    """
    Returned by reset() and every step(). All fields always present.
    Nullable fields use None when not applicable.
    """
    customer_message: str = Field(
        ...,
        description=(
            "The most recent natural-language message from the customer. "
            "Set to the opening complaint on reset(). Updated only by "
            "request_info actions. Unchanged by all other actions."
        ),
    )
    tool_result: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Structured result of the most recent tool call. "
            "None on reset(). Shape varies by action_type — see PRD.md."
        ),
    )
    ticket_status: TicketStatus = Field(
        default=TicketStatus.OPEN,
        description="Current lifecycle status of the ticket.",
    )
    step_count: int = Field(
        default=0,
        ge=0,
        description="Number of step() calls completed so far. 0 after reset().",
    )
    max_steps: int = Field(
        ...,
        gt=0,
        description="Hard step budget for this task. Set from task config.",
    )
    sentiment_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Simulated customer satisfaction. 0.0 = very angry, 1.0 = very "
            "satisfied. Starts at 0.5. Updated by sentiment-affecting actions."
        ),
    )
    available_actions: list[str] = Field(
        default_factory=list,
        description=(
            "Hint list of ActionType string values currently valid. "
            "Always non-empty until ticket is closed. "
            "Computed by environment.py after each step."
        ),
    )
    issues_identified: list[str] = Field(
        default_factory=list,
        description=(
            "IssueType string values the agent has addressed via tool calls. "
            "Populated by tool_router based on actions taken. Starts empty."
        ),
    )
    timeout_flag: bool = Field(
        default=False,
        description=(
            "True only when the episode ends because step_count reached "
            "max_steps without a close_ticket call."
        ),
    )
    episode_id: str = Field(
        ...,
        description="UUID string. Unique per reset() call. Stable across steps.",
    )
    task_id: str = Field(
        ...,
        description=(
            "Which task is running: 'easy_refund', 'billing_dispute', "
            "or 'multi_issue'."
        ),
    )
```

---

### 2.3 `StepResult`

This is the OpenEnv standard return type from `step()`. It wraps the observation
with reward and done flag.

```python
from openenv.core.models import StepResult as BaseStepResult

# Use the OpenEnv base StepResult directly.
# Do not subclass or redefine it.
# Its fields are:
#   observation: SupportObservation
#   reward: float          # always 0.0 on intermediate steps; [0.0, 1.0] on done
#   done: bool             # True when close_ticket called OR timeout
#   info: dict[str, Any]   # optional metadata; use for reward breakdown on done
```

The `info` dict on terminal steps must contain:

```python
{
    "reward_breakdown": {
        "resolution_score": float,   # 0.0–1.0
        "efficiency_score": float,   # 0.0–1.0
        "compliance_score": float,   # 0.0–1.0
        "sentiment_score":  float,   # 0.0–1.0
        "final_reward":     float,   # weighted sum, clamped
    },
    "ground_truth_resolution": str,  # ResolutionType value
    "agent_resolution":        str,  # ResolutionType value agent submitted
    "policy_violations":       list[str],  # policy_ids violated, or []
    "timeout": bool,
}
```

---

## 3. Pydantic Models — Internal State

These models are internal to the server. They are never serialised across the
API boundary. They live in `models.py` alongside the API models.

### 3.1 `TicketState`

The mutable state object for one episode. Created by `reset()`, mutated by
`step()`, read by `grader.py` and `state()`.

```python
from pydantic import BaseModel, Field
from datetime import datetime

class TicketState(BaseModel):
    # Identity
    episode_id:          str
    task_id:             str
    ticket_id:           str

    # Lifecycle
    ticket_status:       TicketStatus      = TicketStatus.OPEN
    step_count:          int               = 0
    max_steps:           int               = 8
    started_at:          datetime          = Field(default_factory=datetime.utcnow)

    # Customer context
    customer_id:         str               = ""
    customer_sentiment:  float             = Field(default=0.5, ge=0.0, le=1.0)

    # Resolution tracking
    resolution:          ResolutionType | None = None
    resolution_summary:  str               = ""
    issues_identified:   list[IssueType]   = Field(default_factory=list)
    issues_resolved:     list[IssueType]   = Field(default_factory=list)

    # Action history
    actions_taken:       list[ActionType]  = Field(default_factory=list)
    messages_sent:       list[str]         = Field(default_factory=list)

    # Refund tracking
    refund_issued:       bool              = False
    refund_amount:       float             = 0.0
    refund_order_id:     str               = ""

    # Escalation tracking
    escalated:           bool              = False
    escalation_team:     EscalationTeam | None = None
    escalation_reason:   EscalationReason | None = None

    # Policy tracking
    policy_violations:   list[str]         = Field(default_factory=list)  # policy_ids
    policies_checked:    list[str]         = Field(default_factory=list)  # policy_ids

    # Info request tracking
    info_requested:      bool              = False
    info_type_requested: InfoType | None   = None

    # Flags
    timeout_flag:        bool              = False
    fraud_flag:          bool              = False   # set by tool_router if order is fraud-flagged
```

---

### 3.2 `EpisodeConfig`

Loaded from `data/tickets.json` at the start of each episode. Read-only during
the episode.

```python
class EpisodeConfig(BaseModel):
    ticket_id:               str
    task_id:                 str
    difficulty:              TaskDifficulty
    max_steps:               int
    optimal_steps:           int
    category:                IssueCategory
    issue_types:             list[IssueType]    # one or more
    opening_message:         str                # the customer's first message
    ground_truth_resolution: ResolutionType
    applicable_policy_ids:   list[str]          # policy_id strings
    customer_id:             str
    order_ids:               list[str]          # one or more order_ids in this ticket
    fraud_flag:              bool = False       # True triggers POL-FRAUD-001 enforcement
    customer_replies:        dict[str, str]     # InfoType.value → canned reply string
    trap_actions:            list[str]          # ActionType.value strings — common wrong moves
    db_seed:                 "DBSeed"           # nested — see below
```

---

### 3.3 `DBSeed`

Nested inside `EpisodeConfig`. Contains all records to seed the episode's
SQLite database on `reset()`.

```python
class DBSeed(BaseModel):
    customers: list["CustomerRecord"]
    orders:    list["OrderRecord"]
    products:  list["ProductRecord"]
```

---

## 4. Pydantic Models — Data Records

These represent rows in the episode's SQLite database. They are also the JSON
shapes inside `db_seed` in `tickets.json`.

### 4.1 `ProductRecord`

```python
class ProductRecord(BaseModel):
    sku:       str             # format: SKU-XXXXXX
    name:      str
    category:  ProductCategory
    price:     float           # USD, > 0.0
    weight_kg: float           # > 0.0
```

### 4.2 `OrderItem`

```python
class OrderItem(BaseModel):
    sku:        str
    name:       str
    quantity:   int    = Field(..., ge=1)
    unit_price: float  = Field(..., gt=0.0)

    @property
    def subtotal(self) -> float:
        return round(self.quantity * self.unit_price, 2)
```

### 4.3 `ShippingAddress`

```python
class ShippingAddress(BaseModel):
    street:  str
    city:    str
    state:   str   # 2-letter US state code
    zip:     str
    country: str = "US"
```

### 4.4 `OrderRecord`

```python
class OrderRecord(BaseModel):
    order_id:         str             # format: ORD-XXXXXX
    customer_id:      str             # format: CUST-XXXXX
    items:            list[OrderItem]
    status:           OrderStatus
    total_amount:     float           # sum of item subtotals, ≥ 0.0
    payment_method:   PaymentMethod
    created_at:       str             # ISO 8601 datetime string
    shipped_at:       str | None = None
    delivered_at:     str | None = None
    tracking_number:  str | None = None
    shipping_address: ShippingAddress
    fraud_flagged:    bool = False

    @property
    def days_since_delivery(self) -> int | None:
        """Returns None if not yet delivered."""
        if self.delivered_at is None:
            return None
        from datetime import datetime, timezone
        delivered = datetime.fromisoformat(self.delivered_at)
        now = datetime.now(timezone.utc)
        return (now - delivered).days
```

### 4.5 `CustomerRecord`

```python
class CustomerRecord(BaseModel):
    customer_id:          str             # format: CUST-XXXXX
    name:                 str
    email:                str
    account_status:       AccountStatus
    loyalty_tier:         LoyaltyTier
    order_history:        list[str]       # list of order_id strings
    total_lifetime_spend: float           = Field(..., ge=0.0)
    open_disputes:        int             = Field(..., ge=0)
```

### 4.6 `PolicyRule`

```python
class PolicyRule(BaseModel):
    policy_id:        str          # format: POL-XXXX-NNN
    category:         str          # "refund" | "fraud" | "shipping" | "account" | "compensation" | "legal"
    rule_description: str          # human-readable rule statement
    conditions:       list[str]    # list of condition strings that must all be true for rule to apply
    required_action:  str | None   # if set, agent MUST do this; None means rule constrains rather than mandates
    forbidden_actions: list[str]   # ActionType.value strings agent must NOT take when this rule applies
```

### 4.7 `KBArticle`

```python
class KBArticle(BaseModel):
    article_id:         str          # format: KB-XXXX
    title:              str
    category:           str          # "shipping" | "billing" | "account" | "returns" | "products"
    content:            str          # plain text, 200–600 words
    related_policy_ids: list[str]    # policy_id strings this article references
```

### 4.8 `RefundRecord`

Internal record created by `issue_refund`. Stored in SQLite `refunds` table.

```python
class RefundRecord(BaseModel):
    refund_id:      str    # format: REF-XXXXXX, generated by tool_router
    order_id:       str
    customer_id:    str
    amount:         float
    refund_type:    RefundType
    reason:         str
    status:         str = "processed"   # always "processed" in simulation
    eta_days:       int = 5
    created_at:     str                 # ISO 8601
```

### 4.9 `EscalationRecord`

Internal record created by `escalate`. Stored in SQLite `escalations` table.

```python
class EscalationRecord(BaseModel):
    escalation_id:  str    # format: ESC-XXXXXX, generated by tool_router
    ticket_id:      str
    reason:         EscalationReason
    team:           EscalationTeam
    notes:          str
    status:         str = "submitted"   # always "submitted" in simulation
    eta_hours:      int = 24
    created_at:     str                 # ISO 8601
```

---

## 5. JSON Schema — tickets.json

**File location:** `data/tickets.json`
**Structure:** A JSON object with a single key `"tickets"` containing an array of
ticket objects. Each ticket is one `EpisodeConfig`.

### 5.1 Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TicketsDataset",
  "type": "object",
  "required": ["tickets"],
  "properties": {
    "tickets": {
      "type": "array",
      "minItems": 20,
      "items": {
        "type": "object",
        "required": [
          "ticket_id", "task_id", "difficulty", "max_steps", "optimal_steps",
          "category", "issue_types", "opening_message", "ground_truth_resolution",
          "applicable_policy_ids", "customer_id", "order_ids",
          "fraud_flag", "customer_replies", "trap_actions", "db_seed"
        ],
        "properties": {
          "ticket_id":               { "type": "string", "pattern": "^TKT-[A-Z0-9]{6}$" },
          "task_id":                 { "type": "string", "enum": ["easy_refund", "billing_dispute", "multi_issue"] },
          "difficulty":              { "type": "string", "enum": ["easy", "medium", "hard"] },
          "max_steps":               { "type": "integer", "minimum": 4 },
          "optimal_steps":           { "type": "integer", "minimum": 2 },
          "category":                { "type": "string" },
          "issue_types":             { "type": "array", "items": { "type": "string" }, "minItems": 1 },
          "opening_message":         { "type": "string", "minLength": 50 },
          "ground_truth_resolution": { "type": "string" },
          "applicable_policy_ids":   { "type": "array", "items": { "type": "string" } },
          "customer_id":             { "type": "string", "pattern": "^CUST-[0-9]{5}$" },
          "order_ids":               { "type": "array", "items": { "type": "string" }, "minItems": 1 },
          "fraud_flag":              { "type": "boolean" },
          "customer_replies": {
            "type": "object",
            "description": "Keys are InfoType.value strings. Values are canned reply strings."
          },
          "trap_actions": {
            "type": "array",
            "items": { "type": "string" },
            "description": "ActionType.value strings that are common but wrong moves for this ticket."
          },
          "db_seed": {
            "type": "object",
            "required": ["customers", "orders", "products"],
            "properties": {
              "customers": { "type": "array", "minItems": 1 },
              "orders":    { "type": "array", "minItems": 1 },
              "products":  { "type": "array", "minItems": 1 }
            }
          }
        }
      }
    }
  }
}
```

### 5.2 Full Example Ticket — Task: `easy_refund`

```json
{
  "ticket_id": "TKT-ER0001",
  "task_id": "easy_refund",
  "difficulty": "easy",
  "max_steps": 8,
  "optimal_steps": 4,
  "category": "product",
  "issue_types": ["wrong_item_received"],
  "opening_message": "Hi, I placed an order two weeks ago for a pair of Sony WH-1000XM5 noise-cancelling headphones in black, but what arrived in the box was a completely different product — a generic Bluetooth speaker I never ordered. The box is still sealed except for when I opened it to check. I'm really frustrated, this was a birthday gift. Can you please sort this out ASAP? My order number is ORD-482910.",
  "ground_truth_resolution": "refund_issued",
  "applicable_policy_ids": ["POL-REFUND-001", "POL-SHIP-001"],
  "customer_id": "CUST-00142",
  "order_ids": ["ORD-482910"],
  "fraud_flag": false,
  "customer_replies": {
    "order_id":        "Yes, my order number is ORD-482910.",
    "photo_evidence":  "I don't have a photo right now but I can take one. Is that really necessary? I clearly got the wrong thing.",
    "account_details": "My email is maya.r@email.com and my name is Maya Rodriguez.",
    "other":           "I'm not sure what else you need — I received the wrong item, that's it."
  },
  "trap_actions": ["escalate", "send_message"],
  "db_seed": {
    "customers": [
      {
        "customer_id":          "CUST-00142",
        "name":                 "Maya Rodriguez",
        "email":                "maya.r@email.com",
        "account_status":       "active",
        "loyalty_tier":         "silver",
        "order_history":        ["ORD-482910", "ORD-391045", "ORD-300812"],
        "total_lifetime_spend": 847.50,
        "open_disputes":        0
      }
    ],
    "orders": [
      {
        "order_id":        "ORD-482910",
        "customer_id":     "CUST-00142",
        "status":          "delivered",
        "total_amount":    349.99,
        "payment_method":  "credit_card",
        "created_at":      "2026-03-10T14:22:00Z",
        "shipped_at":      "2026-03-12T09:15:00Z",
        "delivered_at":    "2026-03-14T16:45:00Z",
        "tracking_number": "1Z999AA10123456784",
        "fraud_flagged":   false,
        "shipping_address": {
          "street":  "42 Maple Avenue",
          "city":    "Austin",
          "state":   "TX",
          "zip":     "78701",
          "country": "US"
        },
        "items": [
          {
            "sku":        "SKU-WH1000",
            "name":       "Sony WH-1000XM5 Wireless Noise-Cancelling Headphones (Black)",
            "quantity":   1,
            "unit_price": 349.99
          }
        ]
      }
    ],
    "products": [
      {
        "sku":       "SKU-WH1000",
        "name":      "Sony WH-1000XM5 Wireless Noise-Cancelling Headphones (Black)",
        "category":  "electronics",
        "price":     349.99,
        "weight_kg": 0.25
      }
    ]
  }
}
```

---

## 6. JSON Schema — policies.json

**File location:** `data/policies.json`
**Structure:** A JSON object with a single key `"policies"` containing an array of
`PolicyRule` objects.

### 6.1 Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PoliciesDataset",
  "type": "object",
  "required": ["policies"],
  "properties": {
    "policies": {
      "type": "array",
      "items": {
        "type": "object",
        "required": [
          "policy_id", "category", "rule_description",
          "conditions", "required_action", "forbidden_actions"
        ],
        "properties": {
          "policy_id":        { "type": "string", "pattern": "^POL-[A-Z]+-[0-9]{3}$" },
          "category":         { "type": "string" },
          "rule_description": { "type": "string", "minLength": 20 },
          "conditions":       { "type": "array", "items": { "type": "string" } },
          "required_action":  { "type": ["string", "null"] },
          "forbidden_actions":{ "type": "array", "items": { "type": "string" } }
        }
      }
    }
  }
}
```

### 6.2 Example Policies

```json
{
  "policies": [

    {
      "policy_id":        "POL-REFUND-001",
      "category":         "refund",
      "rule_description": "Full refund is authorised when the customer returns a product in original condition within the category return window (30 days for electronics and home goods, 60 days for apparel).",
      "conditions": [
        "order status is 'delivered' or 'returned'",
        "days since delivery is within the category return window",
        "item is in original or unopened condition as stated by customer",
        "order is not fraud-flagged"
      ],
      "required_action":   null,
      "forbidden_actions": []
    },

    {
      "policy_id":        "POL-REFUND-002",
      "category":         "refund",
      "rule_description": "Partial refund of 50% of the item price is authorised for items returned after the standard return window but within 90 days of delivery.",
      "conditions": [
        "order status is 'delivered'",
        "days since delivery is between (return_window + 1) and 90 inclusive",
        "order is not fraud-flagged"
      ],
      "required_action":   null,
      "forbidden_actions": ["issue_refund with refund_type=full"]
    },

    {
      "policy_id":        "POL-REFUND-003",
      "category":         "refund",
      "rule_description": "No refund is permitted for any item more than 90 days after delivery, under any circumstances.",
      "conditions": [
        "days since delivery is greater than 90"
      ],
      "required_action":   null,
      "forbidden_actions": ["issue_refund"]
    },

    {
      "policy_id":        "POL-FRAUD-001",
      "category":         "fraud",
      "rule_description": "Any order or transaction flagged as potentially fraudulent must be escalated to the fraud investigation team immediately. The agent must not issue any refund, replacement, or account change on a fraud-flagged order.",
      "conditions": [
        "order.fraud_flagged is true OR issue_type is 'unauthorized_transaction'"
      ],
      "required_action":   "escalate with team=fraud_investigation and reason=potential_fraud",
      "forbidden_actions": ["issue_refund", "close_ticket with resolution != escalated"]
    },

    {
      "policy_id":        "POL-FRAUD-002",
      "category":         "fraud",
      "rule_description": "Any refund amount exceeding $500 USD requires manager approval and must be escalated before the refund is issued.",
      "conditions": [
        "issue_refund.amount > 500.0",
        "order.fraud_flagged is false"
      ],
      "required_action":   "escalate with team=manager and reason=high_value_refund BEFORE calling issue_refund",
      "forbidden_actions": ["issue_refund before escalating"]
    },

    {
      "policy_id":        "POL-SHIP-001",
      "category":         "shipping",
      "rule_description": "Orders not delivered within 14 days of expected delivery date are eligible for either a full refund or a free replacement shipment at the customer's choice.",
      "conditions": [
        "order status is 'shipped' or 'lost_in_transit'",
        "days since expected delivery date exceed 14"
      ],
      "required_action":   null,
      "forbidden_actions": []
    },

    {
      "policy_id":        "POL-SHIP-002",
      "category":         "shipping",
      "rule_description": "Orders with status 'lost_in_transit' are eligible for a full refund or replacement shipment. The agent must offer both options to the customer via send_message or request_info before closing.",
      "conditions": [
        "order status is 'lost_in_transit'"
      ],
      "required_action":   "offer refund or replacement to customer before close_ticket",
      "forbidden_actions": ["close_ticket without first offering refund or replacement"]
    },

    {
      "policy_id":        "POL-ACCT-001",
      "category":         "account",
      "rule_description": "Locked accounts may only be unlocked after the agent completes identity verification by requesting account details from the customer via request_info.",
      "conditions": [
        "customer.account_status is 'locked'",
        "issue_type is 'account_locked'"
      ],
      "required_action":   "request_info with info_type=account_details BEFORE resolving",
      "forbidden_actions": ["close_ticket with resolution=account_unlocked without first calling request_info"]
    },

    {
      "policy_id":        "POL-LEGAL-001",
      "category":         "legal",
      "rule_description": "Any customer message containing explicit legal threats (references to lawyers, lawsuits, courts, or regulatory bodies) must be escalated to the legal team immediately. The agent must not attempt self-resolution.",
      "conditions": [
        "customer message contains keywords: 'lawyer', 'lawsuit', 'sue', 'court', 'attorney', 'legal action', 'ACCC', 'FTC', 'regulatory'"
      ],
      "required_action":   "escalate with team=legal and reason=legal_threat",
      "forbidden_actions": ["issue_refund", "send_message without first escalating"]
    },

    {
      "policy_id":        "POL-COMP-001",
      "category":         "compensation",
      "rule_description": "Goodwill compensation (shop credit) is capped at $25 USD per incident without manager approval. Compensation above $25 requires escalation with reason=manager_review.",
      "conditions": [
        "agent intends to issue shop credit as compensation",
        "compensation amount exceeds $25"
      ],
      "required_action":   "escalate with team=manager and reason=manager_review if amount > 25",
      "forbidden_actions": ["issue_refund with amount > 25 as compensation without escalating"]
    }

  ]
}
```

---

## 7. JSON Schema — knowledge_base.json

**File location:** `data/knowledge_base.json`
**Structure:** A JSON object with a single key `"articles"` containing an array of
`KBArticle` objects.

### 7.1 Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "KnowledgeBase",
  "type": "object",
  "required": ["articles"],
  "properties": {
    "articles": {
      "type": "array",
      "minItems": 10,
      "items": {
        "type": "object",
        "required": ["article_id", "title", "category", "content", "related_policy_ids"],
        "properties": {
          "article_id":         { "type": "string", "pattern": "^KB-[0-9]{4}$" },
          "title":              { "type": "string", "minLength": 10 },
          "category":           { "type": "string", "enum": ["shipping", "billing", "account", "returns", "products"] },
          "content":            { "type": "string", "minLength": 200, "maxLength": 2000 },
          "related_policy_ids": { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  }
}
```

### 7.2 Three Full Example Articles

```json
{
  "articles": [

    {
      "article_id": "KB-0001",
      "title": "How to Process a Return and Refund for a Wrong or Incorrect Item",
      "category": "returns",
      "related_policy_ids": ["POL-REFUND-001", "POL-REFUND-002", "POL-REFUND-003"],
      "content": "If a customer reports receiving the wrong item, the first step is to verify the order by looking up the order record. Confirm the order status is 'delivered' and note the delivery date, as this determines which refund policy applies.\n\nFor orders delivered within the past 30 days (electronics and home goods) or 60 days (apparel), a full refund is authorised under POL-REFUND-001. The customer does not need to physically return the item for wrong-item cases — ShopEasy's policy covers the cost of the fulfilment error.\n\nTo process the refund, use the issue_refund action with refund_type set to 'full' and the amount set to the order's total_amount. Set the reason field to clearly describe the wrong-item situation, such as 'Customer received incorrect item; order contained wrong product.'\n\nFor orders delivered between 31 and 90 days ago (electronics/home goods) or 61 and 90 days ago (apparel), a 50% partial refund applies under POL-REFUND-002. In this case, set refund_type to 'partial' and the amount to exactly 50% of the order total.\n\nFor orders delivered more than 90 days ago, no refund is permitted under POL-REFUND-003. In this case, send a message explaining the policy and close the ticket with resolution set to 'no_action_required'.\n\nAfter issuing the refund, close the ticket with resolution set to 'refund_issued' for full refunds, or 'partial_refund_issued' for partial refunds. Include a clear summary describing what was done and why.\n\nDo not escalate wrong-item cases unless the order is fraud-flagged or the refund amount exceeds $500 USD, which would trigger POL-FRAUD-002."
    },

    {
      "article_id": "KB-0002",
      "title": "Identifying and Resolving Duplicate or Erroneous Billing Charges",
      "category": "billing",
      "related_policy_ids": ["POL-REFUND-001", "POL-FRAUD-001", "POL-FRAUD-002"],
      "content": "Billing disputes involving duplicate charges require careful investigation before any refund is issued. Do not issue a refund until you have fully verified which charge is legitimate and which is erroneous.\n\nBegin by looking up all orders associated with the customer using lookup_order. Check the order dates, amounts, and payment methods carefully. A charge that appears duplicate may in fact be a separate legitimate transaction — for example, a subscription renewal processed on the same day as a product purchase, or two separate orders placed close together.\n\nOnce you have identified the specific duplicate charge, verify it is not fraud-flagged. If the order has fraud_flagged set to true, you must escalate to the fraud investigation team under POL-FRAUD-001 before taking any further action.\n\nIf the charge is confirmed as a genuine duplicate (identical amount, same payment method, no corresponding order record for one of the charges), issue a partial refund for the duplicate amount only. Set refund_type to 'partial', the amount to the duplicate charge value, and provide a clear reason such as 'Duplicate charge identified; one charge of $X.XX has been refunded.'\n\nIf the refund amount for the duplicate charge exceeds $500 USD, you must escalate to the manager team under POL-FRAUD-002 before issuing the refund. After manager escalation, you may proceed with the refund.\n\nDo not refund both charges. Only the confirmed duplicate should be refunded. Refunding a legitimate subscription or order charge is a policy violation under POL-REFUND-001.\n\nClose the ticket with resolution set to 'partial_refund_issued' and include in the summary which specific charge was refunded and why it was identified as a duplicate."
    },

    {
      "article_id": "KB-0003",
      "title": "Account Unlock and Identity Verification Procedure",
      "category": "account",
      "related_policy_ids": ["POL-ACCT-001"],
      "content": "Customer accounts may be locked for several reasons including too many failed login attempts, suspicious activity detected by ShopEasy's security system, or a manual lock placed by a previous support agent.\n\nUnder POL-ACCT-001, a locked account may only be unlocked after successful identity verification. This is a mandatory step — closing a ticket with resolution 'account_unlocked' without first completing identity verification is a policy violation.\n\nTo complete identity verification, use the request_info action with info_type set to 'account_details'. In the message field, ask the customer to confirm their registered email address, full name as it appears on the account, and any recent order number. The simulated customer will reply with this information.\n\nOnce the customer has provided their account details via the request_info response, you may proceed to resolve the account issue. In this environment, the act of successfully calling request_info with info_type='account_details' and receiving a non-error reply is treated as successful verification — no further validation step is needed.\n\nAfter verification, close the ticket with resolution set to 'account_unlocked' and include a summary noting that identity was verified before the account was unlocked.\n\nIf the customer's account status is 'suspended' rather than 'locked', the unlock procedure is not applicable. Suspended accounts require manager review — escalate with team set to 'manager' and reason set to 'manager_review', and close with resolution 'escalated'.\n\nDo not attempt to unlock accounts by calling close_ticket directly without the request_info step. The grader will detect the missing verification step and apply a policy compliance penalty."
    }

  ]
}
```

---

## 8. SQLite Schema

The episode database is created fresh on every `reset()` call, seeded from the
`db_seed` block in the ticket config, and destroyed when the episode ends.
The database file lives at `data/episodes/{episode_id}.db`.

```sql
-- Products table
CREATE TABLE products (
    sku          TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    price        REAL NOT NULL CHECK (price > 0),
    weight_kg    REAL NOT NULL CHECK (weight_kg > 0)
);

-- Customers table
CREATE TABLE customers (
    customer_id           TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    email                 TEXT NOT NULL,
    account_status        TEXT NOT NULL,
    loyalty_tier          TEXT NOT NULL,
    total_lifetime_spend  REAL NOT NULL DEFAULT 0.0,
    open_disputes         INTEGER NOT NULL DEFAULT 0
);

-- Orders table
CREATE TABLE orders (
    order_id         TEXT PRIMARY KEY,
    customer_id      TEXT NOT NULL REFERENCES customers(customer_id),
    status           TEXT NOT NULL,
    total_amount     REAL NOT NULL,
    payment_method   TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    shipped_at       TEXT,
    delivered_at     TEXT,
    tracking_number  TEXT,
    fraud_flagged    INTEGER NOT NULL DEFAULT 0,   -- 0=false, 1=true
    street           TEXT NOT NULL,
    city             TEXT NOT NULL,
    state            TEXT NOT NULL,
    zip              TEXT NOT NULL,
    country          TEXT NOT NULL DEFAULT 'US'
);

-- Order items table
CREATE TABLE order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL REFERENCES orders(order_id),
    sku         TEXT NOT NULL REFERENCES products(sku),
    name        TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity >= 1),
    unit_price  REAL NOT NULL CHECK (unit_price > 0)
);

-- Refunds table (populated by issue_refund tool)
CREATE TABLE refunds (
    refund_id   TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL REFERENCES orders(order_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    amount      REAL NOT NULL CHECK (amount > 0),
    refund_type TEXT NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'processed',
    eta_days    INTEGER NOT NULL DEFAULT 5,
    created_at  TEXT NOT NULL
);

-- Escalations table (populated by escalate tool)
CREATE TABLE escalations (
    escalation_id TEXT PRIMARY KEY,
    ticket_id     TEXT NOT NULL,
    reason        TEXT NOT NULL,
    team          TEXT NOT NULL,
    notes         TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'submitted',
    eta_hours     INTEGER NOT NULL DEFAULT 24,
    created_at    TEXT NOT NULL
);
```

**Seeding procedure in `environment.py`:**
```python
async def _seed_database(self, episode_id: str, config: EpisodeConfig) -> None:
    """
    Called by reset(). Creates the episode DB and inserts all records
    from config.db_seed. Uses aiosqlite for async access.
    """
    db_path = f"data/episodes/{episode_id}.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(CREATE_TABLES_SQL)   # the SQL above as a constant
        for product in config.db_seed.products:
            await db.execute(
                "INSERT INTO products VALUES (?,?,?,?,?)",
                (product.sku, product.name, product.category.value,
                 product.price, product.weight_kg)
            )
        for customer in config.db_seed.customers:
            await db.execute(
                "INSERT INTO customers VALUES (?,?,?,?,?,?,?)",
                (customer.customer_id, customer.name, customer.email,
                 customer.account_status.value, customer.loyalty_tier.value,
                 customer.total_lifetime_spend, customer.open_disputes)
            )
        for order in config.db_seed.orders:
            await db.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (order.order_id, order.customer_id, order.status.value,
                 order.total_amount, order.payment_method.value,
                 order.created_at, order.shipped_at, order.delivered_at,
                 order.tracking_number, int(order.fraud_flagged),
                 order.shipping_address.street, order.shipping_address.city,
                 order.shipping_address.state, order.shipping_address.zip,
                 order.shipping_address.country)
            )
            for item in order.items:
                await db.execute(
                    "INSERT INTO order_items (order_id,sku,name,quantity,unit_price) VALUES (?,?,?,?,?)",
                    (order.order_id, item.sku, item.name, item.quantity, item.unit_price)
                )
        await db.commit()
```

---

## 9. Field Contracts and Invariants

These are hard rules enforced at runtime. A coding agent must implement all of
them. They are not optional.

### 9.1 Reward invariants

```
reward is always float
reward is always in [0.0, 1.0] — use max(0.0, min(1.0, value))
reward is always 0.0 on non-terminal steps
reward is always 0.0 on timeout (step_count >= max_steps without close_ticket)
reward is only non-zero on terminal steps triggered by close_ticket
```

### 9.2 `sentiment_score` invariants

```
sentiment_score starts at exactly 0.5 on reset()
sentiment_score is always float in [0.0, 1.0]
sentiment_score is clamped after every update: max(0.0, min(1.0, score))
sentiment_score is never negative
```

### 9.3 `step_count` invariants

```
step_count starts at 0 after reset()
step_count increments by exactly 1 on every step() call
step_count never decrements
step_count never exceeds max_steps (episode terminates at max_steps)
```

### 9.4 `available_actions` invariants

```
available_actions is never an empty list during an active episode
available_actions contains only ActionType.value strings
available_actions always contains "close_ticket" unless ticket_status == "closed"
After escalate is called: "issue_refund" may be removed (context-dependent)
After close_ticket: available_actions == []
```

### 9.5 `tool_result` invariants

```
tool_result is None after reset()
tool_result is always a dict (never a list or scalar) after any step()
tool_result always contains an "error" key (string) when the tool fails
tool_result never contains raw SQLite row objects — always serialised to dicts
```

### 9.6 ID format contracts

```
episode_id:    UUID4 string e.g. "550e8400-e29b-41d4-a716-446655440000"
ticket_id:     "TKT-" + 6 uppercase alphanumeric chars
order_id:      "ORD-" + 6 digits
customer_id:   "CUST-" + 5 digits
refund_id:     "REF-" + 6 uppercase alphanumeric chars (generated by tool_router)
escalation_id: "ESC-" + 6 uppercase alphanumeric chars (generated by tool_router)
policy_id:     "POL-" + category uppercase + "-" + 3 digits
article_id:    "KB-" + 4 digits
sku:           "SKU-" + 6 alphanumeric chars
```

### 9.7 Monetary invariants

```
All monetary values are float rounded to 2 decimal places
refund amount must be > 0.0 and <= order.total_amount
refund amount > 500.0 triggers POL-FRAUD-002 enforcement
compensation amount > 25.0 triggers POL-COMP-001 enforcement
All amounts stored and returned in USD
```

---

## 10. Import Map

This table tells the coding agent exactly which models to import in each file.
No model should be imported from a file other than `models.py`.

| File                      | Imports from models.py                                                                                                       |
|---------------------------|------------------------------------------------------------------------------------------------------------------------------|
| `server/environment.py`   | `SupportAction`, `SupportObservation`, `StepResult`, `TicketState`, `EpisodeConfig`, `TicketStatus`, `ActionType`           |
| `server/tool_router.py`   | `SupportAction`, `SupportObservation`, `TicketState`, `ActionType`, `OrderRecord`, `RefundRecord`, `EscalationRecord`, all enums |
| `server/grader.py`        | `TicketState`, `EpisodeConfig`, `ResolutionType`, `PolicyRule`                                                               |
| `server/app.py`           | `SupportAction`, `SupportObservation`                                                                                        |
| `server/ticket_generator.py` | `EpisodeConfig`, `DBSeed`, `CustomerRecord`, `OrderRecord`, `ProductRecord`                                               |
| `client.py`               | `SupportAction`, `SupportObservation`, `ActionType`, `ResolutionType`                                                        |
| `baseline.py`             | `SupportAction`, `ActionType`, `ResolutionType`                                                                              |

**Absolute rule:** `grader.py` imports from `models.py` only. It never imports
from `tool_router.py`. `tool_router.py` never imports from `grader.py`.

---

*End of DATA_SCHEMA.md — Version 1.0.0*
*Every model, enum, and field in this document maps directly to production code.*
*When a coding agent is uncertain about a type or field name, this document wins.*