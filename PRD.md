# PRD.md — Customer Support Resolution Gym
## Product Requirements Document — OpenEnv Environment

**Version:** 1.0.0
**Status:** Authoritative specification. All implementation decisions derive from this document.
**Audience:** AI coding agents (Claude Code, Cursor, Windsurf) building this environment from scratch.

---

## 1. Overview

Customer Support Resolution Gym is a multi-turn, tool-using agentic environment built on the OpenEnv framework (meta-pytorch/OpenEnv). It simulates a fictional e-commerce company called **ShopEasy** and trains AI agents to resolve customer support tickets by calling structured tools, reading policy documents, querying order databases, and making resolution decisions. Each episode is one support ticket. The agent must investigate, act, and close the ticket correctly within a step budget.

This environment implements the full OpenEnv specification: typed `Action` and `Observation` models, and the three core API methods — `reset()`, `step()`, and `state()` — served over WebSocket via a FastAPI server packaged in Docker and deployable to Hugging Face Spaces.

---

## 2. Motivation

### 2.1 The Research Gap

The OpenEnv Hub currently contains environments for code execution (`coding_env`), classic games (`atari_env`), and game theory (`OpenSpiel_env`). Every existing environment is either a game or a single-agent programming sandbox. There is no environment in the Hub that requires an agent to:

- Use multiple heterogeneous tools in sequence
- Maintain and update structured state across steps
- Apply policy rules to constrain valid actions
- Handle ambiguous, multi-issue real-world scenarios
- Make escalation vs. resolution decisions under uncertainty

Customer support is the canonical domain for all five of these capabilities. It is a $400B+ industry problem, it is immediately understandable to any judge or researcher, and it maps directly to the multi-turn tool-use capability that frontier LLM research is actively trying to improve.

### 2.2 Why This Domain

- **Verifiable ground truth.** Every ticket has a correct resolution type. The grader does not need an LLM to score — it compares the agent's `close_ticket(resolution)` call against a ground truth enum stored in the ticket config. Scoring is deterministic and reproducible.
- **Natural partial reward structure.** A ticket with three issues can be partially resolved. An agent that handles two of three issues gets meaningful partial credit. This is essential for RL training signal.
- **Multi-step episode structure.** A correctly resolved ticket requires 4–15 ordered tool calls. This creates long-horizon episodes with intermediate state, which is what RL training environments need to generate learning signal.
- **No external dependencies.** The entire simulated world — orders, customers, products, policies, knowledge base — lives in local JSON files and SQLite. The environment runs completely offline inside Docker with zero network calls.

---

## 3. The Simulated World

### 3.1 Company: ShopEasy

ShopEasy is a fictional mid-size e-commerce retailer. It sells products across three categories:

| Category    | Examples                                   | Return Window |
|-------------|--------------------------------------------|---------------|
| Electronics | Laptops, phones, tablets, headphones       | 30 days       |
| Apparel     | Clothing, shoes, accessories               | 60 days       |
| Home Goods  | Kitchen, furniture, decor, appliances      | 30 days       |

All products have a SKU, a name, a price (USD), a category, and a weight (kg).

### 3.2 Order System

Every order in ShopEasy has the following states and transitions:

```
pending → shipped → delivered → (returned | completed)
pending → cancelled
shipped → lost_in_transit
```

Order fields:
- `order_id` — unique string, format `ORD-XXXXXX`
- `customer_id` — unique string, format `CUST-XXXXX`
- `items` — list of `{sku, name, quantity, unit_price}`
- `status` — one of: `pending`, `shipped`, `delivered`, `returned`, `completed`, `cancelled`, `lost_in_transit`
- `total_amount` — float, sum of all items
- `created_at` — ISO 8601 datetime string
- `shipped_at` — ISO 8601 datetime string or null
- `delivered_at` — ISO 8601 datetime string or null
- `tracking_number` — string or null
- `shipping_address` — `{street, city, state, zip, country}`
- `payment_method` — one of: `credit_card`, `debit_card`, `paypal`, `shop_credit`

### 3.3 Customer Records

Every customer has:
- `customer_id` — format `CUST-XXXXX`
- `name` — full name string
- `email` — string
- `account_status` — one of: `active`, `locked`, `suspended`, `pending_verification`
- `loyalty_tier` — one of: `standard`, `silver`, `gold`, `platinum`
- `order_history` — list of order_ids (last 12 months)
- `total_lifetime_spend` — float (USD)
- `open_disputes` — int (count of unresolved tickets)

### 3.4 Policy Rules

ShopEasy has a finite, enumerated set of policies stored in `data/policies.json`. Policies constrain what the agent is allowed to do. The grader checks policy compliance as a reward component.

Key policies (non-exhaustive — full list in `data/policies.json`):

| Policy ID        | Rule                                                                                        |
|------------------|---------------------------------------------------------------------------------------------|
| `POL-REFUND-001` | Full refund allowed if item returned within category return window and in original condition |
| `POL-REFUND-002` | Partial refund (50%) for items returned after return window, up to 90 days                  |
| `POL-REFUND-003` | No refund after 90 days from delivery under any circumstances                               |
| `POL-FRAUD-001`  | Any transaction flagged as potentially fraudulent MUST be escalated — agent cannot self-resolve |
| `POL-FRAUD-002`  | Refunds over $500 require manager approval — agent must escalate, not self-issue             |
| `POL-SHIP-001`   | Orders not delivered within 14 days of expected delivery date are eligible for reship or refund |
| `POL-SHIP-002`   | Lost-in-transit orders: issue full refund OR replacement shipment (customer's choice)       |
| `POL-ACCT-001`   | Account unlock requires identity verification via `request_info` before proceeding          |
| `POL-COMP-001`   | Compensation capped at $25 shop credit for inconvenience unless manager-approved            |
| `POL-LEGAL-001`  | Any message containing legal threats must be escalated immediately — no self-resolution      |

### 3.5 Knowledge Base

ShopEasy has a knowledge base stored in `data/knowledge_base.json`. It contains articles with:
- `article_id` — format `KB-XXXX`
- `title` — string
- `category` — one of: `shipping`, `billing`, `account`, `returns`, `products`
- `content` — string (plain text, 200–600 words)
- `related_policy_ids` — list of policy IDs this article references

The knowledge base is searchable via the `search_kb` action. The agent must search it to understand policies before acting.

---

## 4. Episode Lifecycle

### 4.1 Start of Episode: `reset(task_id)`

The client calls `reset(task_id)` where `task_id` is one of `easy_refund`, `billing_dispute`, or `multi_issue`.

The server:
1. Loads the ticket scenario from `data/tickets.json` matching the task_id
2. Seeds the in-memory SQLite database with the order, customer, and product records for that ticket
3. Initializes a `TicketState` object tracking all mutable episode state
4. Sets `step_count = 0`, `ticket_status = "open"`, `sentiment_score = 0.5`
5. Returns the initial `SupportObservation` containing the customer's opening message

The opening message is a realistic multi-sentence customer complaint in plain English. It may contain one or more issues. It does not explicitly state what action the agent should take.

### 4.2 During Episode: `step(SupportAction)`

The client calls `step(action)` with a `SupportAction` containing an `action_type` and `parameters` dict.

The server:
1. Validates the action (action_type must be a known `ActionType` enum value; parameters must match the schema for that action type)
2. Routes the action to the appropriate handler in `tool_router.py`
3. Executes the handler, which reads/writes the TicketState and SQLite database
4. Updates `step_count += 1`
5. Updates `sentiment_score` based on the action taken (some actions improve sentiment, some degrade it)
6. Calls `grader.score(ticket_state)` — reward is **0.0 on all intermediate steps** (non-terminal)
7. Determines `done`:
   - `done = True` if `action_type == ActionType.CLOSE_TICKET`
   - `done = True` if `step_count >= max_steps` (episode timeout)
   - `done = False` otherwise
8. If `done = True` and action was `CLOSE_TICKET`: calls full grader, returns final reward (0.0–1.0)
9. If `done = True` due to timeout: reward = 0.0
10. Returns `StepResult(observation, reward, done)`

### 4.3 End of Episode: `close_ticket` or timeout

An episode ends in one of two ways:

**Normal termination:** Agent calls `step(SupportAction(action_type=ActionType.CLOSE_TICKET, parameters={"resolution": ResolutionType.X, "summary": "..."}))`. The grader runs the full scoring function and returns a reward in [0.0, 1.0].

**Timeout:** `step_count` reaches `max_steps` without a `close_ticket` call. `done=True`, `reward=0.0`, the observation includes a `timeout_flag=True` field.

### 4.4 State: `state()`

The client can call `state()` at any time to retrieve episode metadata without advancing the episode. Returns the current `TicketState`:
- `episode_id` — unique string for this episode instance
- `task_id` — which task is being run
- `step_count` — current step number
- `max_steps` — step budget for this task
- `ticket_status` — current status string
- `resolved_issues` — list of issue IDs the agent has addressed so far
- `actions_taken` — list of `ActionType` strings in order
- `sentiment_score` — float 0.0–1.0

### 4.5 Concurrency

The environment is concurrent-safe. Each `reset()` call creates a new isolated episode with its own in-memory SQLite database instance (keyed by `episode_id`). Multiple agents can run simultaneous episodes without interference. Set `IS_CONCURRENT = True` in `openenv.yaml`.

---

## 5. Action Space

There are exactly **8 action types**. All are defined in the `ActionType` enum in `models.py`. No other action types exist or will be added.

Each action is called as:
```python
SupportAction(
    action_type=ActionType.<NAME>,
    parameters={...}  # schema defined below per action
)
```

---

### Action 1: `lookup_order`

**Purpose:** Retrieves the full order record for a given order ID from the simulated database.

**Parameters:**
```json
{
  "order_id": "ORD-123456"   // required, string
}
```

**What it does:**
- Queries the episode's SQLite DB for the order matching `order_id`
- If found: returns full order record (status, items, dates, tracking, amounts)
- If not found: returns `{"error": "Order ORD-XXXXXX not found"}`

**State changes:** None. Read-only.

**Effect on sentiment:** None.

**Observation returned:** `tool_result` contains the full order dict or an error dict.

**Error cases:**
- Missing `order_id` parameter: returns validation error, step still counted
- Order belongs to a different customer than the ticket's customer: returns `{"error": "Order does not belong to this customer"}`

---

### Action 2: `check_policy`

**Purpose:** Retrieves a specific policy rule by its policy ID.

**Parameters:**
```json
{
  "policy_id": "POL-REFUND-001"   // required, string
}
```

**What it does:**
- Looks up `policy_id` in the in-memory policy registry (loaded from `data/policies.json`)
- Returns the full policy object: `{policy_id, rule_description, conditions, required_action, forbidden_actions}`
- If not found: returns `{"error": "Policy not found"}`

**State changes:** None. Read-only.

**Effect on sentiment:** None.

**Observation returned:** `tool_result` contains the policy dict or error.

**Error cases:**
- Unknown policy ID: returns error dict, step counted

---

### Action 3: `search_kb`

**Purpose:** Full-text search of the ShopEasy knowledge base.

**Parameters:**
```json
{
  "query": "how to process a refund for wrong item"   // required, string, 5–200 chars
}
```

**What it does:**
- Performs keyword matching against `data/knowledge_base.json` article titles and content
- Returns top-3 matching articles: `[{article_id, title, category, content, related_policy_ids}]`
- If no articles match: returns `{"results": [], "message": "No articles found for query"}`

**State changes:** None. Read-only.

**Effect on sentiment:** None.

**Observation returned:** `tool_result` contains `{"results": [...]}`.

**Error cases:**
- Query shorter than 5 characters: returns validation error

---

### Action 4: `request_info`

**Purpose:** Sends a message to the customer requesting additional information. Simulates the customer replying.

**Parameters:**
```json
{
  "message": "Could you please provide the order number for this transaction?",   // required, string, 10–500 chars
  "info_type": "order_id"   // required, one of: "order_id", "transaction_id", "photo_evidence", "account_details", "other"
}
```

**What it does:**
- Logs the agent's request in `TicketState.actions_taken`
- Triggers the simulated customer reply engine: returns a canned response based on `info_type` and the ticket scenario config
- The customer reply is realistic natural language and is pre-scripted per ticket in `data/tickets.json` under `customer_replies[info_type]`
- If the ticket has no canned reply for this `info_type`: returns `"I'm not sure I understand what you need."`

**State changes:** `TicketState.pending_info_resolved` may update. Certain tasks require `request_info` before `issue_refund` is valid.

**Effect on sentiment:** +0.05 (customer appreciates being asked; shows the agent is engaged).

**Observation returned:** `tool_result` contains `{"customer_reply": "..."}`. The `customer_message` field in the observation is also updated to the customer's reply.

**Error cases:**
- Message under 10 characters: validation error

---

### Action 5: `issue_refund`

**Purpose:** Issues a monetary refund to the customer's original payment method.

**Parameters:**
```json
{
  "order_id": "ORD-123456",   // required, string
  "amount":   49.99,           // required, float, > 0.0
  "reason":   "wrong_item_received",   // required, string, free text, max 200 chars
  "refund_type": "full"        // required, one of: "full", "partial"
}
```

**What it does:**
- Validates the refund amount against the order total (cannot exceed order total)
- Checks policy compliance: consults `POL-REFUND-001/002/003` and `POL-FRAUD-001/002`
- If the order's customer has a fraud flag OR refund amount > $500: sets `policy_violation = True` in TicketState and returns a warning — the grader will penalize this
- If valid: marks the order as refund-pending in the SQLite DB, logs refund record
- Returns `{"refund_id": "REF-XXXXXX", "amount": 49.99, "status": "processed", "eta_days": 5}`

**State changes:** Order status may update to `returned`. `TicketState.refund_issued = True`. `TicketState.refund_amount` set.

**Effect on sentiment:** +0.15 if amount is correct. -0.10 if amount is wrong (over/under). -0.20 if policy violation.

**Observation returned:** `tool_result` contains the refund confirmation or an error.

**Error cases:**
- Amount exceeds order total: returns `{"error": "Refund amount exceeds order total of $X"}`
- Amount is 0 or negative: validation error
- Order not found in current episode DB: returns error

---

### Action 6: `send_message`

**Purpose:** Sends an informational or empathetic message to the customer without requesting information or taking action.

**Parameters:**
```json
{
  "message": "I sincerely apologize for the inconvenience. I am reviewing your order now and will resolve this shortly.",   // required, string, 10–1000 chars
  "message_type": "apology"   // required, one of: "apology", "update", "explanation", "confirmation", "closing"
}
```

**What it does:**
- Logs the message in `TicketState.messages_sent`
- Runs a keyword-based sentiment classifier on the message text
- Updates `sentiment_score` accordingly
- Returns `{"delivered": true, "sentiment_impact": "+0.05"}`

**State changes:** `TicketState.messages_sent` appended. `sentiment_score` updated.

**Effect on sentiment:** +0.05 to +0.10 depending on message type and keyword quality. Sending more than 4 messages: diminishing returns (capped at +0.02 per additional message).

**Observation returned:** `tool_result` contains delivery confirmation and sentiment impact.

**Error cases:**
- Message under 10 characters: validation error

---

### Action 7: `escalate`

**Purpose:** Escalates the ticket to a human manager or specialist team. This is mandatory for certain issue types per policy.

**Parameters:**
```json
{
  "reason": "potential_fraud",          // required, EscalationReason enum
  "team": "fraud_investigation",        // required, one of: "fraud_investigation", "manager", "legal", "technical", "billing_specialist"
  "notes": "Customer reports unauthorized $750 charge. Order ORD-123456 flagged."   // required, string, 20–500 chars
}
```

**`EscalationReason` enum values:**
`potential_fraud`, `legal_threat`, `high_value_refund`, `account_security`, `technical_issue`, `manager_review`, `policy_exception`

**What it does:**
- Sets `TicketState.escalated = True`
- Sets `TicketState.escalation_team` to the target team
- Logs the escalation in `TicketState.actions_taken`
- Returns `{"escalation_id": "ESC-XXXXXX", "team": "...", "eta_hours": 24, "status": "submitted"}`
- After escalation, the episode can still be closed with `close_ticket(resolution=ResolutionType.ESCALATED)`

**State changes:** `TicketState.escalated = True`. Further `issue_refund` calls after escalation return a warning (but are not blocked).

**Effect on sentiment:** +0.10 (customer knows it's being taken seriously). -0.05 if escalated unnecessarily (grader detects).

**Observation returned:** `tool_result` contains escalation confirmation.

**Error cases:**
- `notes` under 20 characters: validation error
- Invalid `team` value: validation error

---

### Action 8: `close_ticket`

**Purpose:** Closes the episode and triggers final reward scoring. Must be the last action called.

**Parameters:**
```json
{
  "resolution": "refund_issued",   // required, ResolutionType enum
  "summary": "Customer received wrong item. Full refund of $49.99 issued to original payment method. Replacement not requested."   // required, string, 20–500 chars
}
```

**`ResolutionType` enum values:**
`refund_issued`, `partial_refund_issued`, `replacement_shipped`, `escalated`, `account_unlocked`, `information_provided`, `no_action_required`, `compensation_issued`, `multiple_resolutions`

**What it does:**
- Sets `TicketState.ticket_status = "closed"`
- Sets `TicketState.resolution = resolution`
- Triggers the full grader: computes all 4 reward components and returns final reward
- Returns `{"ticket_id": "...", "resolution": "...", "final_score": 0.85, "breakdown": {...}}`

**State changes:** `TicketState.ticket_status = "closed"`. `done = True`.

**Effect on sentiment:** N/A — episode is ending.

**Observation returned:** `tool_result` contains the closure confirmation and score breakdown (for debugging). The `StepResult.reward` contains the canonical reward value.

**Error cases:**
- `summary` under 20 characters: validation error, episode still ends, reward = 0.0
- Calling `close_ticket` when `ticket_status` is already `"closed"`: returns error, no-op

---

## 6. Observation Space

Every call to `reset()` and `step()` returns a `SupportObservation` object. All fields are always present. Nullable fields use `None` when not applicable.

| Field                | Type                  | Description                                                                 |
|----------------------|-----------------------|-----------------------------------------------------------------------------|
| `customer_message`   | `str`                 | The most recent message from the customer. On reset, this is the opening complaint. Updated by `request_info`. Unchanged by other actions. |
| `tool_result`        | `dict \| None`        | The structured result of the most recent tool call. `None` on `reset()`.   |
| `ticket_status`      | `str`                 | Current ticket status: `"open"`, `"in_progress"`, `"escalated"`, `"closed"` |
| `step_count`         | `int`                 | Number of steps taken so far. 0 on reset.                                  |
| `max_steps`          | `int`                 | Maximum steps allowed for this task before timeout.                        |
| `sentiment_score`    | `float`               | Customer sentiment 0.0 (very angry) to 1.0 (very satisfied). Starts at 0.5.|
| `available_actions`  | `list[str]`           | Hint list of currently valid `ActionType` string values. Always non-empty. After escalation, `issue_refund` may be removed. After `close_ticket`, list is empty. |
| `issues_identified`  | `list[str]`           | Issue type strings the agent has explicitly addressed so far (populated by tool_router based on actions taken). Starts empty. |
| `timeout_flag`       | `bool`                | `True` only when the episode ends due to step budget exhaustion. `False` otherwise. |
| `episode_id`         | `str`                 | Unique identifier for this episode instance. Stable across all steps.      |
| `task_id`            | `str`                 | The task being run: `"easy_refund"`, `"billing_dispute"`, or `"multi_issue"`. |

---

## 7. Reward Function Overview

> Full specification is in `REWARD_SPEC.md`. This section is a summary only.

The final reward is computed only when `done = True` via a `close_ticket` action. Intermediate steps always return `reward = 0.0`. Timeout returns `reward = 0.0`.

**Four components, always summing to a float in [0.0, 1.0]:**

| Component              | Weight | What it measures                                                     |
|------------------------|--------|----------------------------------------------------------------------|
| Resolution correctness | 0.55   | Did the agent's `resolution` enum match the ground truth?           |
| Step efficiency        | 0.20   | How close to optimal step count? (optimal / actual, capped at 1.0) |
| Policy compliance      | 0.15   | Were all applicable policy rules respected?                         |
| Customer sentiment     | 0.10   | What is `sentiment_score` at episode end?                           |

**Final formula:**
```
reward = clamp(
    (resolution_score * 0.55) +
    (efficiency_score * 0.20) +
    (compliance_score * 0.15) +
    (sentiment_score  * 0.10),
    0.0, 1.0
)
```

---

## 8. The Three Tasks

### Task 1 — `easy_refund` (Easy)
- **Max steps:** 8
- **Optimal steps:** 4
- **Scenario:** Customer received the wrong item. Order exists. Within return window. Standard full refund applies.
- **Correct resolution:** `ResolutionType.refund_issued`
- **Baseline agent expected score:** ~0.55
- **LLM agent expected score:** ~0.85

### Task 2 — `billing_dispute` (Medium)
- **Max steps:** 14
- **Optimal steps:** 7
- **Scenario:** Customer reports a double charge. One charge is a legitimate subscription renewal, one is a duplicate. Agent must distinguish them and issue a partial refund for the duplicate only.
- **Correct resolution:** `ResolutionType.partial_refund_issued`
- **Baseline agent expected score:** ~0.30
- **LLM agent expected score:** ~0.65

### Task 3 — `multi_issue` (Hard)
- **Max steps:** 25
- **Optimal steps:** 12
- **Scenario:** Customer has three issues: account locked, an unauthorized transaction (must escalate per `POL-FRAUD-001`), and a late delivery eligible for compensation. Agent must handle all three correctly.
- **Correct resolution:** `ResolutionType.multiple_resolutions`
- **Baseline agent expected score:** ~0.10
- **LLM agent expected score:** ~0.42

> Full task specifications including exact ticket text, order states, ground truth, and optimal action sequences are in `TASKS.md`.

---

## 9. OpenEnv Spec Compliance

This environment implements the full OpenEnv specification:

| Requirement                          | Implementation                                              |
|--------------------------------------|-------------------------------------------------------------|
| Typed Action model                   | `SupportAction(Action)` in `models.py`                     |
| Typed Observation model              | `SupportObservation(Observation)` in `models.py`           |
| `reset()` method                     | `SupportEnvironment.reset()` in `server/environment.py`    |
| `step()` method                      | `SupportEnvironment.step()` in `server/environment.py`     |
| `state()` method                     | `SupportEnvironment.state()` in `server/environment.py`    |
| `openenv.yaml` manifest              | Root-level `openenv.yaml`                                  |
| Reward in [0.0, 1.0]                 | Enforced by `grader.py` with `clamp()`                     |
| Minimum 3 tasks                      | `easy_refund`, `billing_dispute`, `multi_issue`            |
| Agent grader per task                | Task-specific grader configs in `TASKS.md`                 |
| Baseline inference script            | `baseline.py` — rule-based agent, reproducible scores      |
| Docker + HF Spaces deployment        | `server/Dockerfile`, deployed via `openenv push`           |
| Concurrency support                  | Per-episode SQLite DB, `IS_CONCURRENT = True`              |

---

## 10. Out of Scope

The following are explicitly **not** part of this environment. An AI coding agent reading this document must not implement any of the following:

| What                              | Why excluded                                                                 |
|-----------------------------------|------------------------------------------------------------------------------|
| Real payment processing           | All transactions are simulated. No Stripe, PayPal, or payment API calls.    |
| Real email sending                | Customer messages are simulated canned responses. No SMTP, no SendGrid.     |
| External API calls of any kind    | Environment runs fully offline. No HTTP requests from inside `environment.py`. |
| LLM calls inside the environment  | The environment is a sandbox. It must not call OpenAI, Anthropic, or any LLM. |
| Frontend / UI                     | No Gradio, Streamlit, or React. The web interface is the OpenEnv built-in at `/web`. |
| Authentication / API keys         | No bearer tokens, no JWT, no API key validation on endpoints.               |
| PostgreSQL, Redis, or MongoDB     | SQLite only. All data is seeded fresh per episode from JSON files.          |
| Persistent sessions               | Sessions do not persist across `reset()` calls. Each episode is independent. |
| Multi-agent scenarios             | One agent per episode. No coordination between agents.                      |
| Real customer data                | All customers, orders, and messages are entirely fictional.                 |
| More than 8 action types          | The action space is fixed at 8. No new actions will be added in this version. |
| More than 3 tasks                 | Three tasks cover easy/medium/hard. No additional tasks in v1.0.            |

---

## 11. Success Criteria

This environment is considered **complete and submission-ready** when all of the following pass:

- [ ] `python baseline.py` runs without errors and prints scores for all 3 tasks to stdout
- [ ] A random agent (choosing actions uniformly at random) scores < 0.10 on all 3 tasks
- [ ] An optimal hand-coded agent scores ≥ 0.95 on `easy_refund`
- [ ] The reward for any episode ending in timeout is exactly 0.0
- [ ] The reward for a correctly resolved episode with optimal steps is ≥ 0.90
- [ ] `docker build . && docker run -p 8000:8000 .` starts the server successfully
- [ ] `openenv push --repo-id <username>/customer-support-gym` deploys to HF Spaces
- [ ] The live HF Spaces URL responds to `reset()` and `step()` calls from `baseline.py`
- [ ] `state()` returns valid data at every point during an episode
- [ ] All three tasks produce reward values strictly in the range [0.0, 1.0] with no exceptions

---

## 12. Glossary

| Term              | Definition                                                                   |
|-------------------|------------------------------------------------------------------------------|
| Episode           | One complete ticket from `reset()` to `close_ticket()` or timeout           |
| Task              | A named episode configuration with a fixed scenario, difficulty, and budget  |
| TicketState       | The mutable internal state object tracking all episode progress              |
| Ground truth      | The correct `ResolutionType` stored in the ticket config — used by grader   |
| Policy compliance | Whether the agent's actions respected all applicable `PolicyRule` objects    |
| Sentiment score   | Float [0.0, 1.0] tracking simulated customer satisfaction during the episode |
| Optimal steps     | The minimum number of steps required to perfectly resolve a task             |
| Tool router       | The module mapping `ActionType` → handler function in `tool_router.py`      |

---

*End of PRD.md — Version 1.0.0*
*This document is the authoritative specification. When in doubt, defer to this document.*