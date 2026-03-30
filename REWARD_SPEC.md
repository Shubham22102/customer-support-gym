# REWARD_SPEC.md — Customer Support Resolution Gym
## Reward Function Specification

**Version:** 1.0.0
**Authority:** This document is the single source of truth for `grader.py`.
Every formula, weight, edge case, and worked example here must be implemented
exactly. Do not interpret. Do not simplify. Do not add components.

---

## 1. Overview

The reward function scores a completed episode by combining four independent
components. It runs exactly once — when the agent calls `close_ticket` and
`done=True`. Every non-terminal step returns `reward = 0.0`.

**Final formula:**

```
reward = clamp(
    (R  * 0.55) +
    (E  * 0.20) +
    (C  * 0.15) +
    (S  * 0.10),
    0.0,
    1.0
)
```

Where:
- `R` = Resolution Score (0.0–1.0)
- `E` = Efficiency Score (0.0–1.0)
- `C` = Compliance Score (0.0–1.0)
- `S` = Sentiment Score (0.0–1.0)
- `clamp(x, 0.0, 1.0)` = `max(0.0, min(1.0, x))`

**Timeout rule:** If the episode ends because `step_count >= max_steps` without
a `close_ticket` call, `reward = 0.0` unconditionally. The formula is not run.

---

## 2. Component R — Resolution Score (weight: 0.55)

### 2.1 What it measures

Whether the agent chose the correct `ResolutionType` when closing the ticket,
and whether all required sub-issues within the ticket were addressed.

### 2.2 Formula

```python
def compute_resolution_score(state: TicketState, config: EpisodeConfig) -> float:
    # Guard: ticket must be closed via close_ticket, not timeout
    if state.timeout_flag:
        return 0.0
    if state.resolution is None:
        return 0.0

    agent_res   = state.resolution            # ResolutionType
    ground_res  = config.ground_truth_resolution  # ResolutionType

    # Step 1: base score from resolution match
    base = _resolution_match_score(agent_res, ground_res)

    # Step 2: issue coverage multiplier (only for multi_issue task)
    if config.task_id == "multi_issue":
        coverage = _issue_coverage_score(state, config)
        return round(base * coverage, 4)

    return round(base, 4)
```

### 2.3 Resolution match lookup table

```python
def _resolution_match_score(agent: ResolutionType, ground: ResolutionType) -> float:
    if agent == ground:
        return 1.0

    # Partial credit: wrong type but same semantic family
    FAMILIES = {
        "refund_family":       {ResolutionType.REFUND_ISSUED,
                                ResolutionType.PARTIAL_REFUND_ISSUED,
                                ResolutionType.COMPENSATION_ISSUED},
        "shipping_family":     {ResolutionType.REPLACEMENT_SHIPPED,
                                ResolutionType.REFUND_ISSUED},
        "escalation_family":   {ResolutionType.ESCALATED},
        "account_family":      {ResolutionType.ACCOUNT_UNLOCKED,
                                ResolutionType.INFORMATION_PROVIDED},
        "info_family":         {ResolutionType.INFORMATION_PROVIDED,
                                ResolutionType.NO_ACTION_REQUIRED},
    }
    for family in FAMILIES.values():
        if agent in family and ground in family:
            return 0.4   # same family, wrong specific type

    return 0.0  # completely wrong category
```

**Complete lookup table for grader tests:**

| Agent resolution             | Ground truth                 | Score |
|------------------------------|------------------------------|-------|
| `refund_issued`              | `refund_issued`              | 1.00  |
| `partial_refund_issued`      | `partial_refund_issued`      | 1.00  |
| `escalated`                  | `escalated`                  | 1.00  |
| `account_unlocked`           | `account_unlocked`           | 1.00  |
| `multiple_resolutions`       | `multiple_resolutions`       | 1.00  |
| `partial_refund_issued`      | `refund_issued`              | 0.40  |
| `refund_issued`              | `partial_refund_issued`      | 0.40  |
| `compensation_issued`        | `refund_issued`              | 0.40  |
| `replacement_shipped`        | `refund_issued`              | 0.40  |
| `information_provided`       | `account_unlocked`           | 0.40  |
| `no_action_required`         | `information_provided`       | 0.40  |
| `escalated`                  | `refund_issued`              | 0.00  |
| `refund_issued`              | `escalated`                  | 0.00  |
| `no_action_required`         | `refund_issued`              | 0.00  |
| `account_unlocked`           | `refund_issued`              | 0.00  |

### 2.4 Issue coverage score (multi_issue task only)

The `multi_issue` task has three required issue types in `config.issue_types`.
The base resolution score is multiplied by the fraction of issues the agent
addressed (logged in `state.issues_resolved`).

```python
def _issue_coverage_score(state: TicketState, config: EpisodeConfig) -> float:
    required = set(config.issue_types)          # e.g. {ACCOUNT_LOCKED, UNAUTHORIZED_TRANSACTION, LATE_DELIVERY}
    resolved = set(state.issues_resolved)
    if not required:
        return 1.0
    coverage = len(required & resolved) / len(required)
    return round(coverage, 4)
```

**Coverage examples for multi_issue:**

| Issues resolved by agent        | Required issues | Coverage | R (if base=1.0) |
|---------------------------------|-----------------|----------|-----------------|
| All 3 correct                   | 3               | 1.00     | 1.00            |
| 2 of 3 correct                  | 3               | 0.67     | 0.67            |
| 1 of 3 correct                  | 3               | 0.33     | 0.33            |
| 0 of 3 correct                  | 3               | 0.00     | 0.00            |

---

## 3. Component E — Efficiency Score (weight: 0.20)

### 3.1 What it measures

How close the agent's step count was to the optimal (minimum required) steps
for this task. Rewards concise, focused agents. Penalises agents that call
redundant tools or send unnecessary messages.

### 3.2 Formula

```python
def compute_efficiency_score(state: TicketState, config: EpisodeConfig) -> float:
    if state.timeout_flag:
        return 0.0

    optimal = config.optimal_steps    # from ticket config
    actual  = state.step_count        # how many steps the agent actually took

    if actual <= 0:
        return 0.0

    if actual <= optimal:
        # Finished in optimal steps or fewer — perfect efficiency
        return 1.0

    # Efficiency degrades linearly beyond optimal
    # At 2× optimal steps → score = 0.0
    max_steps = config.max_steps
    excess    = actual - optimal
    budget    = max_steps - optimal   # steps available beyond optimal

    if budget <= 0:
        return 1.0  # optimal == max_steps, no room to be inefficient

    score = 1.0 - (excess / budget)
    return round(max(0.0, score), 4)
```

**Efficiency score table — easy_refund (optimal=4, max=8, budget=4):**

| Steps taken | Excess | Score       |
|-------------|--------|-------------|
| 1–4         | 0      | 1.00        |
| 5           | 1      | 0.75        |
| 6           | 2      | 0.50        |
| 7           | 3      | 0.25        |
| 8           | 4      | 0.00        |

**Efficiency score table — billing_dispute (optimal=7, max=14, budget=7):**

| Steps taken | Excess | Score       |
|-------------|--------|-------------|
| 1–7         | 0      | 1.00        |
| 8           | 1      | 0.857       |
| 10          | 3      | 0.571       |
| 12          | 5      | 0.286       |
| 14          | 7      | 0.00        |

**Efficiency score table — multi_issue (optimal=12, max=25, budget=13):**

| Steps taken | Excess | Score       |
|-------------|--------|-------------|
| 1–12        | 0      | 1.00        |
| 14          | 2      | 0.846       |
| 18          | 6      | 0.538       |
| 22          | 10     | 0.231       |
| 25          | 13     | 0.00        |

---

## 4. Component C — Compliance Score (weight: 0.15)

### 4.1 What it measures

Whether the agent respected every `PolicyRule` that applied to this ticket.
Compliance is checked against `config.applicable_policy_ids`.

### 4.2 Formula

```python
def compute_compliance_score(state: TicketState, config: EpisodeConfig) -> float:
    applicable = config.applicable_policy_ids   # list of policy_id strings
    if not applicable:
        return 1.0  # no policies apply → full compliance by default

    violations = set(state.policy_violations)   # populated by tool_router
    violated_applicable = [p for p in applicable if p in violations]

    n_applicable = len(applicable)
    n_violated   = len(violated_applicable)
    n_respected  = n_applicable - n_violated

    score = n_respected / n_applicable
    return round(max(0.0, score), 4)
```

### 4.3 How policy violations are recorded

`tool_router.py` sets violations on `TicketState.policy_violations` when:

| Trigger                                                        | Policy violated     | How tool_router detects it                                   |
|----------------------------------------------------------------|---------------------|--------------------------------------------------------------|
| `issue_refund` called on fraud-flagged order                   | `POL-FRAUD-001`     | `order.fraud_flagged == True` in DB                          |
| `issue_refund` called with `amount > 500` without prior escalation | `POL-FRAUD-002` | `amount > 500` and `state.escalated == False`                |
| `issue_refund` with `refund_type=full` when days > return window and ≤ 90 | `POL-REFUND-002` | `order.days_since_delivery > window` and `≤ 90`         |
| `issue_refund` called when `days_since_delivery > 90`          | `POL-REFUND-003`    | `order.days_since_delivery > 90`                             |
| `close_ticket(resolution=account_unlocked)` without prior `request_info(info_type=account_details)` | `POL-ACCT-001` | `InfoType.ACCOUNT_DETAILS not in state.info_types_requested` |
| Any action taken after legal threat detected without prior escalation | `POL-LEGAL-001` | Legal keywords in `state.customer_messages` and `state.escalated == False` |

**Compliance score examples:**

| Applicable policies         | Violations          | Score             |
|-----------------------------|---------------------|-------------------|
| `[POL-REFUND-001]`          | `[]`                | 1.00              |
| `[POL-REFUND-001, POL-SHIP-001]` | `[]`           | 1.00              |
| `[POL-REFUND-001, POL-FRAUD-001]` | `[POL-FRAUD-001]` | 0.50          |
| `[POL-FRAUD-001, POL-FRAUD-002, POL-ACCT-001]` | `[POL-FRAUD-001, POL-FRAUD-002]` | 0.33 |
| `[POL-REFUND-001]`          | `[POL-REFUND-001]`  | 0.00              |

---

## 5. Component S — Sentiment Score (weight: 0.10)

### 5.1 What it measures

The simulated customer's satisfaction level at the end of the episode. This is
`state.customer_sentiment` — a float in [0.0, 1.0] that evolves during the
episode based on agent actions.

### 5.2 Formula

```python
def compute_sentiment_score(state: TicketState) -> float:
    return round(max(0.0, min(1.0, state.customer_sentiment)), 4)
```

Sentiment is already normalised — the grader reads it directly from state.

### 5.3 Sentiment delta rules (implemented in `tool_router.py`, NOT grader)

These deltas are applied by `tool_router.py` after each action. They accumulate
across the episode. Always clamp after applying.

```python
SENTIMENT_DELTAS = {
    # Positive deltas
    ActionType.REQUEST_INFO:    +0.05,   # agent shows engagement
    ActionType.ISSUE_REFUND:    None,    # conditional — see below
    ActionType.SEND_MESSAGE:    None,    # conditional — see below
    ActionType.ESCALATE:        +0.10,   # issue is being taken seriously
    ActionType.CLOSE_TICKET:    +0.05,   # resolution communicated

    # Neutral / negative
    ActionType.LOOKUP_ORDER:    +0.00,
    ActionType.CHECK_POLICY:    +0.00,
    ActionType.SEARCH_KB:       +0.00,
}
```

**`issue_refund` conditional deltas:**
```python
def refund_sentiment_delta(amount: float, order_total: float, policy_violation: bool) -> float:
    if policy_violation:
        return -0.20   # refund attempted but blocked/flagged
    ratio = amount / order_total
    if ratio >= 0.95:
        return +0.20   # full or near-full refund — customer very happy
    elif ratio >= 0.45:
        return +0.10   # meaningful partial refund
    else:
        return +0.02   # token refund — small positive
```

**`send_message` conditional deltas:**
```python
def message_sentiment_delta(message: str, message_type: MessageType, msg_count: int) -> float:
    # Base delta by message type
    base = {
        MessageType.APOLOGY:      +0.08,
        MessageType.UPDATE:       +0.05,
        MessageType.EXPLANATION:  +0.04,
        MessageType.CONFIRMATION: +0.06,
        MessageType.CLOSING:      +0.03,
    }.get(message_type, +0.03)

    # Diminishing returns after 3 messages
    if msg_count > 3:
        base = base * 0.3

    # Keyword boost: empathetic language
    empathy_words = ["apologize", "sorry", "understand", "frustrating",
                     "appreciate", "patience", "priority"]
    if any(w in message.lower() for w in empathy_words):
        base += 0.03

    return round(min(base, 0.12), 4)  # cap per-message at 0.12
```

**Sentiment starting value and bounds:**
```
Initial value:  0.5  (neutral)
Minimum:        0.0  (extremely angry — cannot go negative)
Maximum:        1.0  (very satisfied — cannot exceed)
Apply clamp after every delta: max(0.0, min(1.0, current + delta))
```

---

## 6. Full Reward Formula (assembled)

```python
class Grader:
    def score(
        self,
        state: TicketState,
        config: EpisodeConfig,
    ) -> tuple[float, dict[str, Any]]:

        # Timeout: no scoring needed
        if state.timeout_flag:
            breakdown = {
                "resolution_score": 0.0,
                "efficiency_score": 0.0,
                "compliance_score": 0.0,
                "sentiment_score":  round(state.customer_sentiment, 4),
                "final_reward":     0.0,
            }
            return 0.0, breakdown

        R = compute_resolution_score(state, config)
        E = compute_efficiency_score(state, config)
        C = compute_compliance_score(state, config)
        S = compute_sentiment_score(state)

        raw    = (R * 0.55) + (E * 0.20) + (C * 0.15) + (S * 0.10)
        reward = round(max(0.0, min(1.0, raw)), 4)

        breakdown = {
            "resolution_score": R,
            "efficiency_score": E,
            "compliance_score": C,
            "sentiment_score":  S,
            "final_reward":     reward,
            "ground_truth_resolution": config.ground_truth_resolution.value,
            "agent_resolution":        state.resolution.value if state.resolution else None,
            "policy_violations":       list(state.policy_violations),
            "timeout":                 False,
        }
        return reward, breakdown
```

---

## 7. Worked Examples

Three complete episode traces showing step-by-step state evolution and final
score computation.

---

### Example A — Perfect run on `easy_refund`

**Task config:** max_steps=8, optimal_steps=4, ground_truth=`refund_issued`,
applicable_policies=[`POL-REFUND-001`], issue_types=[`wrong_item_received`]

**Episode trace:**

```
reset()
  → sentiment=0.5, step_count=0

Step 1: lookup_order(order_id="ORD-482910")
  → tool_result: {order found, status=delivered, total=349.99, days_since_delivery=14, fraud_flagged=false}
  → sentiment_delta: +0.00  → sentiment=0.50
  → step_count=1

Step 2: check_policy(policy_id="POL-REFUND-001")
  → tool_result: {policy found, full refund within 30 days}
  → sentiment_delta: +0.00  → sentiment=0.50
  → step_count=2

Step 3: issue_refund(order_id="ORD-482910", amount=349.99, reason="Wrong item received", refund_type="full")
  → order.days_since_delivery=14 ≤ 30 → no policy violation
  → refund_ratio = 349.99/349.99 = 1.0 → delta=+0.20
  → sentiment=0.50+0.20=0.70
  → state.refund_issued=True, state.refund_amount=349.99
  → step_count=3

Step 4: close_ticket(resolution="refund_issued", summary="Customer received wrong item. Full refund of $349.99 issued.")
  → sentiment_delta: +0.05  → sentiment=0.70+0.05=0.75
  → done=True
  → step_count=4
```

**Scoring:**

```
R: agent=refund_issued, ground=refund_issued  → match=1.0 → R = 1.0
E: actual=4, optimal=4, excess=0              → E = 1.0
C: applicable=[POL-REFUND-001], violations=[] → 1/1 respected → C = 1.0
S: sentiment=0.75                             → S = 0.75

raw    = (1.0 * 0.55) + (1.0 * 0.20) + (1.0 * 0.15) + (0.75 * 0.10)
       = 0.55 + 0.20 + 0.15 + 0.075
       = 0.975
reward = clamp(0.975, 0.0, 1.0) = 0.9750
```

---

### Example B — Suboptimal run on `billing_dispute`

**Task config:** max_steps=14, optimal_steps=7, ground_truth=`partial_refund_issued`,
applicable_policies=[`POL-REFUND-001`, `POL-FRAUD-001`], issue_types=[`duplicate_charge`]

Agent looks up order, sends 4 messages (too many), issues the wrong full refund
instead of partial, and closes with wrong resolution type. Takes 10 steps.

**Episode trace (abbreviated):**

```
reset()  → sentiment=0.5, step_count=0

Step 1:  lookup_order(order_id="ORD-512300")    → step_count=1
Step 2:  send_message(apology)                  → sentiment=0.5+0.08+0.03(empathy)=0.61, step_count=2
Step 3:  send_message(update)                   → sentiment=0.61+0.05=0.66, step_count=3
Step 4:  send_message(explanation)              → sentiment=0.66+0.04=0.70, step_count=4
Step 5:  send_message(update)                   → msg_count=4>3 → delta=0.05*0.3=0.015 → sentiment=0.715, step_count=5
Step 6:  check_policy(POL-REFUND-001)           → step_count=6
Step 7:  lookup_order(order_id="ORD-512301")    → step_count=7
Step 8:  request_info(info_type="transaction_id") → sentiment=0.715+0.05=0.765, step_count=8
Step 9:  issue_refund(amount=89.99, refund_type="full", ...)
         → ground truth requires partial refund (duplicate only = $44.99)
         → issuing full refund on a dispute ticket where partial applies
         → POL-REFUND-002 violation recorded (refund_type=full when partial required)
         → refund_ratio=89.99/89.99=1.0 but policy_violation=True → delta=-0.20
         → sentiment=0.765-0.20=0.565, step_count=9
Step 10: close_ticket(resolution="refund_issued", ...)
         → done=True, step_count=10
```

**Scoring:**

```
R: agent=refund_issued, ground=partial_refund_issued
   → same refund_family → match=0.4 → R = 0.40

E: actual=10, optimal=7, excess=3, budget=(14-7)=7
   → score = 1.0 - (3/7) = 1.0 - 0.4286 = 0.5714 → E = 0.5714

C: applicable=[POL-REFUND-001, POL-FRAUD-001]
   violations=[POL-REFUND-002]  ← POL-REFUND-002 is NOT in applicable_policy_ids
   violated_applicable = []     ← no applicable policy was violated
   → C = 1.0
   (Note: POL-REFUND-002 violation is recorded but not in applicable_policy_ids
    for this task, so it does not reduce compliance score here)

S: sentiment=0.565 → S = 0.565

raw    = (0.40 * 0.55) + (0.5714 * 0.20) + (1.0 * 0.15) + (0.565 * 0.10)
       = 0.2200 + 0.1143 + 0.1500 + 0.0565
       = 0.5408
reward = clamp(0.5408, 0.0, 1.0) = 0.5408
```

---

### Example C — Timeout on `multi_issue`

**Task config:** max_steps=25, optimal_steps=12, ground_truth=`multiple_resolutions`

Agent calls `lookup_order` and `search_kb` repeatedly but never reaches
`close_ticket`. Hits max_steps=25.

```
After 25 steps without close_ticket:
  done=True, timeout_flag=True

Scoring:
  timeout_flag=True → reward = 0.0 unconditionally

breakdown = {
    "resolution_score": 0.0,
    "efficiency_score": 0.0,
    "compliance_score": 0.0,
    "sentiment_score":  0.61,   # whatever it was at timeout
    "final_reward":     0.0,
    "timeout":          True,
}
```

---

### Example D — Policy violation on `multi_issue` (fraud escalation skipped)

**Scenario:** The ticket has `fraud_flag=True` on the unauthorized transaction.
The agent issues a refund directly without escalating first.

```
Step 5: issue_refund(order_id="ORD-721000", amount=240.00, ...)
  → order.fraud_flagged=True
  → tool_router records POL-FRAUD-001 in state.policy_violations
  → sentiment_delta=-0.20 (policy violation)
  → sentiment drops from 0.65 to 0.45

Step 12: close_ticket(resolution="multiple_resolutions", ...)
  → done=True, step_count=12
```

**Scoring:**

```
R: agent=multiple_resolutions, ground=multiple_resolutions → match=1.0
   issue_coverage: resolved={account_locked, late_delivery} out of
                   required={account_locked, unauthorized_transaction, late_delivery}
   → coverage = 2/3 = 0.667
   → R = 1.0 * 0.667 = 0.667

E: actual=12, optimal=12, excess=0 → E = 1.0

C: applicable=[POL-FRAUD-001, POL-ACCT-001, POL-SHIP-001]
   violations=[POL-FRAUD-001]
   violated_applicable=[POL-FRAUD-001]  → 1 of 3 violated
   → C = 2/3 = 0.667

S: sentiment=0.45 → S = 0.45

raw    = (0.667 * 0.55) + (1.0 * 0.20) + (0.667 * 0.15) + (0.45 * 0.10)
       = 0.3669 + 0.2000 + 0.1001 + 0.0450
       = 0.7120
reward = clamp(0.7120, 0.0, 1.0) = 0.7120
```

This shows: the agent got a good score even with a fraud violation, because
resolution and efficiency were strong. The compliance penalty costs 0.05 in
this case.

---

## 8. Grader Unit Test Vectors

These are the exact inputs and expected outputs for `test_grader.py`. Every
test must pass before submission.

```python
# test_grader.py

def make_state(**overrides) -> TicketState:
    defaults = dict(
        episode_id="test-episode-001",
        task_id="easy_refund",
        ticket_id="TKT-ER0001",
        ticket_status=TicketStatus.CLOSED,
        step_count=4,
        max_steps=8,
        customer_id="CUST-00142",
        customer_sentiment=0.75,
        resolution=ResolutionType.REFUND_ISSUED,
        resolution_summary="Full refund issued.",
        issues_identified=[IssueType.WRONG_ITEM_RECEIVED],
        issues_resolved=[IssueType.WRONG_ITEM_RECEIVED],
        actions_taken=[ActionType.LOOKUP_ORDER, ActionType.CHECK_POLICY,
                       ActionType.ISSUE_REFUND, ActionType.CLOSE_TICKET],
        refund_issued=True,
        refund_amount=349.99,
        escalated=False,
        policy_violations=[],
        timeout_flag=False,
    )
    defaults.update(overrides)
    return TicketState(**defaults)

def make_config(**overrides) -> EpisodeConfig:
    # minimal config for easy_refund
    ...

# Test 1: Perfect easy_refund
def test_perfect_easy_refund():
    state  = make_state()
    config = make_config(task_id="easy_refund", optimal_steps=4,
                         ground_truth_resolution=ResolutionType.REFUND_ISSUED,
                         applicable_policy_ids=["POL-REFUND-001"])
    reward, breakdown = Grader().score(state, config)
    assert reward == 0.975
    assert breakdown["resolution_score"] == 1.0
    assert breakdown["efficiency_score"] == 1.0
    assert breakdown["compliance_score"] == 1.0
    assert breakdown["sentiment_score"]  == 0.75

# Test 2: Timeout always returns 0.0
def test_timeout_zero():
    state = make_state(timeout_flag=True, step_count=8)
    config = make_config()
    reward, breakdown = Grader().score(state, config)
    assert reward == 0.0
    assert breakdown["timeout"] is True

# Test 3: Wrong resolution, same family → 0.4 base
def test_wrong_resolution_same_family():
    state = make_state(resolution=ResolutionType.PARTIAL_REFUND_ISSUED)
    config = make_config(ground_truth_resolution=ResolutionType.REFUND_ISSUED,
                         applicable_policy_ids=[])
    reward, _ = Grader().score(state, config)
    # R=0.4, E=1.0, C=1.0, S=0.75
    # raw = 0.4*0.55 + 1.0*0.20 + 1.0*0.15 + 0.75*0.10
    #     = 0.22 + 0.20 + 0.15 + 0.075 = 0.645
    assert abs(reward - 0.645) < 0.001

# Test 4: Policy violation reduces C
def test_policy_violation():
    state = make_state(policy_violations=["POL-FRAUD-001"])
    config = make_config(applicable_policy_ids=["POL-FRAUD-001", "POL-REFUND-001"])
    _, breakdown = Grader().score(state, config)
    assert breakdown["compliance_score"] == 0.5

# Test 5: Reward always clamped to [0.0, 1.0]
def test_reward_never_exceeds_1():
    state = make_state(customer_sentiment=1.0)
    config = make_config()
    reward, _ = Grader().score(state, config)
    assert 0.0 <= reward <= 1.0

# Test 6: Reward is always float
def test_reward_is_float():
    state  = make_state()
    config = make_config()
    reward, _ = Grader().score(state, config)
    assert isinstance(reward, float)
```

---

## 9. Common Implementation Mistakes

These are errors a coding agent frequently makes. The grader must NOT do any
of these:

| Mistake                                                    | Correct behaviour                                         |
|------------------------------------------------------------|-----------------------------------------------------------|
| Return reward > 0.0 on non-terminal steps                  | Always return 0.0 until `done=True`                       |
| Skip the clamp on the final reward                         | Always `max(0.0, min(1.0, raw))`                          |
| Run the grader on timeout episodes                         | Return `0.0` immediately if `timeout_flag=True`           |
| Count policy_violations not in applicable_policy_ids       | Only violations of applicable policies reduce score C     |
| Apply sentiment deltas inside grader                       | Sentiment is updated by `tool_router.py` — grader reads it |
| Use integer division for coverage ratio                    | Use `float` division: `len(a) / len(b)`, not `//`         |
| Return the breakdown as a flat reward float                | Always return `tuple[float, dict]`                        |
| Apply issue_coverage multiplier to non-multi_issue tasks   | Coverage multiplier only applies to `task_id == "multi_issue"` |

---

*End of REWARD_SPEC.md — Version 1.0.0*