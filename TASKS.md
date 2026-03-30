# TASKS.md — Customer Support Resolution Gym
## Three Task Specifications with Ground Truth

**Version:** 1.0.0
**Authority:** This document defines the three tasks the grader evaluates
agents against. Each task section contains: the exact scenario, the
complete database state, the ground truth resolution, the optimal action
sequence, the trap actions that fool naive agents, and the expected scores
for baseline and LLM agents.

---

## How Tasks Relate to tickets.json

Each task corresponds to one or more tickets in `data/tickets.json` identified
by `task_id`. The `ticket_generator.py` selects a ticket by `task_id` on
each `reset()` call. In v1.0 each task has exactly one canonical ticket
(future versions may have multiple tickets per task for variety).

```
task_id="easy_refund"     → ticket_id="TKT-ER0001"
task_id="billing_dispute" → ticket_id="TKT-BD0001"
task_id="multi_issue"     → ticket_id="TKT-MI0001"
```

---

## Task 1 — `easy_refund`

### 1.1 Metadata

```
task_id:           easy_refund
ticket_id:         TKT-ER0001
difficulty:        easy
max_steps:         8
optimal_steps:     4
category:          product
issue_types:       [wrong_item_received]
ground_truth:      refund_issued
applicable_policy_ids: [POL-REFUND-001, POL-SHIP-001]
fraud_flag:        false
```

### 1.2 Customer Opening Message

```
Hi, I placed an order two weeks ago for a pair of Sony WH-1000XM5
noise-cancelling headphones in black, but what arrived in the box was a
completely different product — a generic Bluetooth speaker I never ordered.
The box is still sealed except for when I opened it to check. I'm really
frustrated, this was a birthday gift. Can you please sort this out ASAP?
My order number is ORD-482910.
```

### 1.3 Database State at Episode Start

**Customer:**
```
customer_id:          CUST-00142
name:                 Maya Rodriguez
email:                maya.r@email.com
account_status:       active
loyalty_tier:         silver
total_lifetime_spend: 847.50
open_disputes:        0
```

**Order ORD-482910:**
```
status:            delivered
total_amount:      349.99
payment_method:    credit_card
created_at:        2026-03-10T14:22:00Z
shipped_at:        2026-03-12T09:15:00Z
delivered_at:      2026-03-14T16:45:00Z
days_since_delivery: 14
fraud_flagged:     false
items:
  - sku: SKU-WH1000
    name: Sony WH-1000XM5 Wireless Noise-Cancelling Headphones (Black)
    quantity: 1
    unit_price: 349.99
```

**Policy context:**
- `POL-REFUND-001` applies: delivered 14 days ago, within 30-day electronics
  return window, full refund authorised
- No fraud flag → `POL-FRAUD-001` does not apply
- Refund amount $349.99 ≤ $500 → `POL-FRAUD-002` does not apply

### 1.4 Ground Truth and Rationale

```
ground_truth_resolution: refund_issued
```

**Rationale:** Order delivered 14 days ago. Electronics return window is 30
days. Customer received wrong item (ShopEasy's fulfilment error). Full refund
is unambiguously correct under `POL-REFUND-001`. No escalation needed.
Replacement was not requested. Resolution type is `refund_issued`.

### 1.5 Optimal Action Sequence (4 steps)

```
Step 1: lookup_order(order_id="ORD-482910")
        Purpose: confirm order exists, is delivered, check fraud flag, note total
        Expected result: order found, status=delivered, total=349.99, fraud_flagged=false

Step 2: check_policy(policy_id="POL-REFUND-001")
        Purpose: confirm full refund is authorised within 30-day window
        Expected result: policy found, full refund valid within return window

Step 3: issue_refund(
            order_id="ORD-482910",
            amount=349.99,
            reason="Customer received wrong item. Fulfilment error by ShopEasy.",
            refund_type="full"
        )
        Purpose: process the full refund
        Expected result: refund_id=REF-XXXXXX, status=processed, eta_days=5

Step 4: close_ticket(
            resolution="refund_issued",
            summary="Customer received wrong item instead of ordered Sony WH-1000XM5 headphones.
                     Full refund of $349.99 issued to original credit card. Expected 5 business days."
        )
        Purpose: end the episode with correct resolution
        Expected result: done=True, reward computed
```

**Expected score on optimal path:**
```
R = 1.00  (exact resolution match)
E = 1.00  (4 steps = optimal)
C = 1.00  (no policy violations)
S = 0.75  (sentiment after refund: 0.5 + 0.20 refund + 0.05 close = 0.75)
reward = (1.00*0.55) + (1.00*0.20) + (1.00*0.15) + (0.75*0.10) = 0.975
```

### 1.6 Trap Actions (common mistakes)

| Trap action                                   | Why it is wrong                                                     | Score impact            |
|-----------------------------------------------|---------------------------------------------------------------------|-------------------------|
| `escalate` before trying to resolve           | No escalation trigger exists here; unnecessary escalation wastes steps and doesn't improve score | E decreases |
| `send_message` × 3 before looking up order   | Agent should look up order first; repeated messages waste steps    | E decreases             |
| `issue_refund(amount=0.50 * 349.99)`          | Full refund applies (POL-REFUND-001); issuing 50% is wrong         | R drops to 0.40         |
| `close_ticket(resolution="replacement_shipped")` | Customer did not request replacement; refund is correct          | R drops to 0.40         |
| `close_ticket(resolution="escalated")`        | No escalation trigger; completely wrong family                     | R = 0.00                |
| Skip `lookup_order`, go straight to `issue_refund` | Risky; order might not exist. Also misses fraud flag check.   | C may decrease if fraud |

### 1.7 Customer Replies (canned responses for `request_info`)

```json
{
  "order_id":        "Yes, my order number is ORD-482910.",
  "transaction_id":  "I'm not sure what transaction ID you mean. The order is ORD-482910.",
  "photo_evidence":  "I don't have a photo right now but I can take one. Is that really necessary? I clearly got the wrong thing.",
  "account_details": "My email is maya.r@email.com and my name is Maya Rodriguez.",
  "other":           "I'm not sure what else you need — I received the wrong item, that's it."
}
```

### 1.8 Expected Scores

| Agent type            | Expected score | Notes                                          |
|-----------------------|----------------|------------------------------------------------|
| Random agent          | 0.02–0.08      | Rarely picks correct resolution by chance      |
| Rule-based baseline   | 0.55–0.65      | Finds order and refunds but takes extra steps  |
| LLM agent (GPT-4o)    | 0.82–0.92      | Usually gets correct path with minor variation |
| Optimal hand-coded    | 0.975          | 4 steps, exact resolution, no violations       |

---

## Task 2 — `billing_dispute`

### 2.1 Metadata

```
task_id:           billing_dispute
ticket_id:         TKT-BD0001
difficulty:        medium
max_steps:         14
optimal_steps:     7
category:          billing
issue_types:       [duplicate_charge]
ground_truth:      partial_refund_issued
applicable_policy_ids: [POL-REFUND-001, POL-FRAUD-001, POL-FRAUD-002]
fraud_flag:        false
```

### 2.2 Customer Opening Message

```
Hi there. I was checking my credit card statement and noticed I've been
charged twice for the same amount — $89.99 — on March 15th. One is for my
ShopEasy subscription renewal which I understand, but the second charge
looks like a duplicate. I've never seen two charges on the same day before.
I'd like the duplicate refunded please. I'm worried this might be some kind
of billing error on your side. My account email is j.chen@fastmail.com.
```

### 2.3 Database State at Episode Start

**Customer:**
```
customer_id:          CUST-00891
name:                 James Chen
email:                j.chen@fastmail.com
account_status:       active
loyalty_tier:         gold
total_lifetime_spend: 2341.00
open_disputes:        0
```

**Order ORD-512300 (subscription renewal — LEGITIMATE):**
```
status:          completed
total_amount:    89.99
payment_method:  credit_card
created_at:      2026-03-15T08:00:00Z
delivered_at:    2026-03-15T08:00:00Z
fraud_flagged:   false
items:
  - sku: SKU-SUBSM
    name: ShopEasy Monthly Subscription — March 2026
    quantity: 1
    unit_price: 89.99
```

**Order ORD-512301 (duplicate charge — ERRONEOUS):**
```
status:          pending
total_amount:    89.99
payment_method:  credit_card
created_at:      2026-03-15T08:02:00Z
delivered_at:    null
shipped_at:      null
tracking_number: null
fraud_flagged:   false
items:
  - sku: SKU-SUBSM
    name: ShopEasy Monthly Subscription — March 2026
    quantity: 1
    unit_price: 89.99
notes: "Duplicate order — created by billing system error at 08:02 UTC."
```

**Policy context:**
- `POL-FRAUD-001`: neither order is fraud-flagged → does not mandate escalation
- `POL-FRAUD-002`: refund amount $89.99 ≤ $500 → no manager escalation required
- `POL-REFUND-001`: the duplicate charge can be refunded without return window concerns
  (it was never fulfilled — status is pending)

### 2.4 Ground Truth and Rationale

```
ground_truth_resolution: partial_refund_issued
```

**Rationale:** One charge is legitimate (subscription renewal, completed).
One charge is erroneous (duplicate billing system error, pending, no
fulfilment). Only the duplicate charge should be refunded — the subscription
charge is valid. Refunding both would itself be a policy violation. The
correct amount to refund is exactly $89.99 (the value of ORD-512301 only).
Because only one of the two charges is refunded, this is a `partial_refund_issued`
resolution, not `refund_issued`.

### 2.5 Optimal Action Sequence (7 steps)

```
Step 1: lookup_order(order_id="ORD-512300")
        Purpose: confirm the subscription renewal order (legitimate charge)
        Expected result: status=completed, amount=$89.99, sku=SKU-SUBSM

Step 2: lookup_order(order_id="ORD-512301")
        Purpose: confirm the duplicate order (erroneous charge)
        Expected result: status=pending, amount=$89.99, no shipped_at, same sku

Step 3: search_kb(query="duplicate charge billing error refund policy")
        Purpose: find KB article on billing dispute procedure
        Expected result: KB-0002 returned (billing dispute article)

Step 4: check_policy(policy_id="POL-FRAUD-001")
        Purpose: verify neither order is fraud-flagged before proceeding
        Expected result: conditions not met (no fraud flag) → no escalation required

Step 5: request_info(
            message="To confirm, you have two charges of $89.99 on March 15th —
                     one for your subscription renewal (ORD-512300) and one that
                     appears to be a duplicate (ORD-512301). Is that correct?",
            info_type="transaction_id"
        )
        Purpose: confirm with customer which charges they see, signal engagement
        Expected result: customer confirms duplicate, provides their view

Step 6: issue_refund(
            order_id="ORD-512301",
            amount=89.99,
            reason="Duplicate charge identified on ORD-512301. Billing system error.
                    ORD-512300 subscription renewal is legitimate and not refunded.",
            refund_type="partial"
        )
        Purpose: refund ONLY the duplicate — critical to use refund_type="partial"
        Expected result: REF-XXXXXX processed, eta=5 days

Step 7: close_ticket(
            resolution="partial_refund_issued",
            summary="Confirmed duplicate charge of $89.99 on ORD-512301 caused by
                     billing system error. Partial refund of $89.99 issued to credit
                     card. Subscription charge ORD-512300 is valid and retained."
        )
        Purpose: close with correct resolution type
        Expected result: done=True
```

**Expected score on optimal path:**
```
R = 1.00  (exact match: partial_refund_issued)
E = 1.00  (7 steps = optimal)
C = 1.00  (no violations; fraud check done, refund ≤ $500)
S = 0.70  (0.5 + 0.05 request_info + 0.10 partial refund + 0.05 close = 0.70)
reward = (1.00*0.55) + (1.00*0.20) + (1.00*0.15) + (0.70*0.10) = 0.97
```

### 2.6 Trap Actions (common mistakes)

| Trap action                                        | Why it is wrong                                                               | Score impact              |
|----------------------------------------------------|-------------------------------------------------------------------------------|---------------------------|
| `issue_refund(order_id="ORD-512300", ...)`         | Refunding the legitimate subscription is wrong; violates POL-REFUND-001       | C decreases, R may drop   |
| `issue_refund(amount=179.98, refund_type="full")`  | Refunding both charges is incorrect; duplicate only is $89.99                 | C decreases; R drops       |
| `issue_refund(refund_type="full")`                 | Should be "partial" because only one of two charges is refunded               | R drops to 0.40            |
| `close_ticket(resolution="refund_issued")`         | Wrong type — only part of the billing was refunded                            | R drops to 0.40            |
| `escalate` without checking fraud flag first       | POL-FRAUD-001 does not apply here; unnecessary escalation wastes steps        | E decreases                |
| Lookup only one order and assume both are wrong    | Agent must look up both orders to distinguish legitimate from duplicate       | R likely wrong             |

### 2.7 Customer Replies

```json
{
  "transaction_id":  "Yes, I can see two separate charges of $89.99 on March 15th on my statement. One says 'ShopEasy Subscription' and the other just says 'ShopEasy' with no description.",
  "order_id":        "I have two order confirmation emails both dated March 15th. One is ORD-512300 and the other is ORD-512301.",
  "account_details": "My email is j.chen@fastmail.com. Account name James Chen.",
  "photo_evidence":  "I can send a screenshot of my bank statement if that helps?",
  "other":           "I just want the duplicate charge refunded. I understand the subscription is valid."
}
```

### 2.8 Expected Scores

| Agent type            | Expected score | Notes                                                               |
|-----------------------|----------------|---------------------------------------------------------------------|
| Random agent          | 0.01–0.05      | Extremely unlikely to pick partial_refund_issued correctly          |
| Rule-based baseline   | 0.28–0.38      | May refund wrong order or use full instead of partial               |
| LLM agent (GPT-4o)    | 0.60–0.72      | Usually identifies duplicate but sometimes picks wrong amount/type  |
| Optimal hand-coded    | 0.97           | 7 steps, partial refund on correct order, exact resolution          |

---

## Task 3 — `multi_issue`

### 3.1 Metadata

```
task_id:           multi_issue
ticket_id:         TKT-MI0001
difficulty:        hard
max_steps:         25
optimal_steps:     12
category:          account
issue_types:       [account_locked, unauthorized_transaction, late_delivery]
ground_truth:      multiple_resolutions
applicable_policy_ids: [POL-FRAUD-001, POL-ACCT-001, POL-SHIP-001, POL-COMP-001]
fraud_flag:        true
```

### 3.2 Customer Opening Message

```
I am absolutely furious right now and I need this sorted immediately.
Three things have gone wrong at once. First, I can't log into my account —
it says it's locked and I have no idea why. Second, I just noticed an
unauthorised charge of $240 on my card for an order I never placed
(ORD-721000). This looks like fraud. Third, my actual order ORD-718842
for a kitchen stand mixer was supposed to arrive last Thursday and it still
hasn't shown up — tracking hasn't updated in 9 days. I need all three of
these resolved today. My account is under the email priya.s@webmail.com.
```

### 3.3 Database State at Episode Start

**Customer:**
```
customer_id:          CUST-03341
name:                 Priya Sharma
email:                priya.s@webmail.com
account_status:       locked
loyalty_tier:         platinum
total_lifetime_spend: 7820.00
open_disputes:        0
```

**Order ORD-721000 (FRAUDULENT — never placed by customer):**
```
status:          shipped
total_amount:    240.00
payment_method:  credit_card
created_at:      2026-03-18T03:14:00Z
shipped_at:      2026-03-18T04:00:00Z
delivered_at:    null
fraud_flagged:   TRUE              ← CRITICAL: triggers POL-FRAUD-001
items:
  - sku: SKU-ELEC09
    name: Portable Power Station 500W
    quantity: 1
    unit_price: 240.00
notes: "Order placed at 03:14 UTC from unrecognised IP. Flagged by fraud detection."
```

**Order ORD-718842 (LEGITIMATE — late delivery):**
```
status:          shipped
total_amount:    189.95
payment_method:  credit_card
created_at:      2026-03-12T10:30:00Z
shipped_at:      2026-03-13T08:00:00Z
delivered_at:    null
expected_delivery: 2026-03-20T00:00:00Z
days_past_expected: 8               ← 8 days past expected delivery
tracking_number: 1Z999AA10198765432
tracking_last_update: 2026-03-19T11:00:00Z   ← 9 days ago
fraud_flagged:   false
items:
  - sku: SKU-KIT22
    name: KitchenPro Stand Mixer 6.5Qt (Brushed Steel)
    quantity: 1
    unit_price: 189.95
```

**Policy context:**
- `POL-FRAUD-001` MANDATORY: ORD-721000 has `fraud_flagged=True` →
  agent MUST escalate to fraud_investigation team before any other action
  on that order. Agent must NOT issue refund on it.
- `POL-ACCT-001` MANDATORY: account is locked → agent MUST call
  `request_info(info_type="account_details")` before resolving account issue.
- `POL-SHIP-001` applies: ORD-718842 is 8 days past expected delivery →
  eligible for refund or replacement.
- `POL-COMP-001` applies: agent may offer up to $25 shop credit compensation
  for inconvenience without manager approval.

### 3.4 Ground Truth and Rationale

```
ground_truth_resolution: multiple_resolutions
```

**Rationale:** Three separate issues require three separate resolutions:

1. **Account locked** → resolve via identity verification + account unlock →
   partial resolution `account_unlocked`
2. **Unauthorized transaction** → this is fraud-flagged →
   MUST escalate to fraud_investigation → partial resolution `escalated`
3. **Late delivery** → 8 days past expected, tracking stale →
   eligible for refund or replacement under POL-SHIP-001 →
   agent must offer customer choice → partial resolution `refund_issued`
   or `replacement_shipped`

Because multiple distinct resolutions are applied in one ticket,
the overall resolution type is `multiple_resolutions`.

### 3.5 Optimal Action Sequence (12 steps)

```
Step 1: request_info(
            message="I'm sorry to hear you're dealing with multiple issues at once.
                     To get started and verify your identity so I can unlock your
                     account, could you please confirm your full name and the email
                     address registered on your ShopEasy account?",
            info_type="account_details"
        )
        Purpose: POL-ACCT-001 compliance — identity verification before account unlock
        Expected result: customer provides name=Priya Sharma, email=priya.s@webmail.com

Step 2: lookup_order(order_id="ORD-721000")
        Purpose: investigate the reported unauthorised charge
        Expected result: fraud_flagged=TRUE, amount=240.00, status=shipped

Step 3: escalate(
            reason="potential_fraud",
            team="fraud_investigation",
            notes="Customer reports unauthorised charge of $240 on ORD-721000.
                   Order placed at 03:14 UTC from unrecognised IP. Order is fraud-flagged
                   in system. Customer has not authorised this purchase. Escalating per
                   POL-FRAUD-001 for investigation and card protection."
        )
        Purpose: POL-FRAUD-001 MANDATORY — fraud-flagged order must be escalated
        Expected result: escalation_id=ESC-XXXXXX, team=fraud_investigation

Step 4: send_message(
            message="I've escalated the unauthorised charge on your account to our
                     fraud investigation team as a priority. They will contact you
                     within 24 hours and ensure your card is protected. You will not
                     be liable for this charge.",
            message_type="update"
        )
        Purpose: inform customer about fraud escalation
        Expected result: delivered, sentiment improves

Step 5: lookup_order(order_id="ORD-718842")
        Purpose: investigate the late delivery
        Expected result: status=shipped, 8 days past expected, tracking stale

Step 6: search_kb(query="late delivery tracking not updated compensation policy")
        Purpose: find KB article on late delivery resolution options
        Expected result: KB article on shipping delays returned

Step 7: check_policy(policy_id="POL-SHIP-001")
        Purpose: confirm eligibility for refund or replacement
        Expected result: 14-day rule confirmed; 8 days past expected = eligible

Step 8: request_info(
            message="For your stand mixer order ORD-718842, the tracking has not
                     updated in 9 days and it appears to be delayed significantly.
                     You are eligible for either a full refund of $189.95 or a
                     free replacement shipment. Which would you prefer?",
            info_type="other"
        )
        Purpose: offer customer choice per POL-SHIP-002 spirit; shows engagement
        Expected result: customer requests refund or replacement

Step 9: issue_refund(
            order_id="ORD-718842",
            amount=189.95,
            reason="Order ORD-718842 not delivered 8 days past expected date.
                    Tracking stale for 9 days. Full refund issued per POL-SHIP-001.",
            refund_type="full"
        )
        Purpose: resolve the late delivery with full refund
        Expected result: refund processed

Step 10: send_message(
             message="I've also added a $15 shop credit to your account as a sincere
                      apology for the inconvenience of dealing with multiple issues
                      today. I truly appreciate your patience.",
             message_type="apology"
         )
         Purpose: goodwill gesture under POL-COMP-001 ($15 < $25 cap — no escalation needed)
         Expected result: customer sentiment improves

Step 11: send_message(
             message="Your account has been unlocked following identity verification.
                      You should be able to log in now. If you experience any further
                      issues accessing your account please do not hesitate to contact us.",
             message_type="confirmation"
         )
         Purpose: communicate account unlock resolution to customer
         Expected result: issue marked as resolved in state

Step 12: close_ticket(
             resolution="multiple_resolutions",
             summary="Three issues resolved: (1) Account unlocked after identity
                      verification per POL-ACCT-001. (2) Unauthorised charge ORD-721000
                      escalated to fraud investigation team per POL-FRAUD-001 —
                      ESC-XXXXXX raised. (3) Late delivery ORD-718842 resolved with
                      full refund of $189.95 per POL-SHIP-001. $15 shop credit applied
                      as goodwill compensation."
         )
         Expected result: done=True, all 3 issues in issues_resolved
```

**Expected score on optimal path:**
```
R: agent=multiple_resolutions, ground=multiple_resolutions → base=1.0
   issue_coverage: resolved={account_locked, unauthorized_transaction, late_delivery}
                   required={account_locked, unauthorized_transaction, late_delivery}
   coverage=3/3=1.0 → R = 1.0 * 1.0 = 1.00

E: actual=12, optimal=12, excess=0 → E = 1.00

C: applicable=[POL-FRAUD-001, POL-ACCT-001, POL-SHIP-001, POL-COMP-001]
   violations=[] → C = 1.00

S: 0.50 (base)
   +0.05 (request_info step 1)
   +0.10 (escalate step 3)
   +0.05 (send_message step 4)
   +0.05 (request_info step 8)
   +0.20 (full refund step 9, ratio=1.0)
   +0.05 (send_message step 10 — apology + empathy words)
   +0.03 (send_message step 11 — empathy)
   +0.05 (close step 12)
   = 0.50 + 0.58 = 1.0 (clamped to 1.0)
   S = 1.00

reward = (1.00*0.55) + (1.00*0.20) + (1.00*0.15) + (1.00*0.10) = 1.00
```

### 3.6 Trap Actions (common mistakes)

| Trap action                                          | Why it is wrong                                                                   | Score impact               |
|------------------------------------------------------|-----------------------------------------------------------------------------------|----------------------------|
| `issue_refund(order_id="ORD-721000", ...)`           | MANDATORY fraud escalation must happen first; violates POL-FRAUD-001              | C drops 0.25; R may drop   |
| `escalate` without looking up order first            | Should confirm fraud flag via `lookup_order` before escalating (good practice)    | Minor; E decreases slightly |
| `close_ticket(resolution="escalated")`               | Only one of three issues was escalated; two others still need resolution          | R = 0.00 (wrong family)    |
| Skip `request_info(info_type="account_details")`     | Violates POL-ACCT-001; `account_unlocked` resolution gets compliance penalty      | C drops 0.25               |
| `issue_refund(order_id="ORD-721000", amount=240.00)` | Same as first trap; fraud-flagged order cannot be self-refunded                   | POL-FRAUD-001 violation     |
| Forget late delivery and only resolve 2 of 3 issues  | Issue coverage = 2/3 = 0.667; R degrades even with correct resolution type       | R = 0.667 instead of 1.0   |
| `close_ticket(resolution="refund_issued")`           | Multiple issues were resolved; correct type is `multiple_resolutions`             | R = 0.00 (wrong family)    |
| Offer compensation >$25 without escalating first     | Violates POL-COMP-001; grader records violation                                   | C drops 0.25               |

### 3.7 Customer Replies

```json
{
  "account_details": "My full name is Priya Sharma and my registered email is priya.s@webmail.com. I've been a customer for 4 years.",
  "transaction_id":  "The charge shows as $240 on March 18th around 3am which is obviously not me — I was asleep. I have no idea what ORD-721000 is.",
  "order_id":        "My real order is ORD-718842 for the stand mixer. That's the one that hasn't arrived.",
  "photo_evidence":  "I can send a photo of the bank statement showing the fraudulent charge if you need it.",
  "other":           "For the mixer — I'd prefer a refund at this point. I can't trust the delivery anymore given everything that's gone wrong."
}
```

### 3.8 Issues Resolved Tracking

For the grader's `_issue_coverage_score` to work correctly, `tool_router.py`
must populate `state.issues_resolved` when the corresponding resolution action
is successfully taken:

| Action taken                                              | Adds to `issues_resolved`         |
|-----------------------------------------------------------|-----------------------------------|
| `escalate(reason="potential_fraud", team="fraud_investigation")` | `IssueType.UNAUTHORIZED_TRANSACTION` |
| `issue_refund(order_id="ORD-718842", ...)`                | `IssueType.LATE_DELIVERY`         |
| `request_info(info_type="account_details")` + `send_message(message_type="confirmation")` | `IssueType.ACCOUNT_LOCKED` |
| `close_ticket` with `resolution="multiple_resolutions"`   | Does not add; triggers grader     |

**Note:** `ACCOUNT_LOCKED` is marked resolved when:
`state.info_type_requested == InfoType.ACCOUNT_DETAILS` AND a confirmation
`send_message` has been sent. The `tool_router.py` must check both conditions.

### 3.9 Expected Scores

| Agent type            | Expected score | Notes                                                                     |
|-----------------------|----------------|---------------------------------------------------------------------------|
| Random agent          | 0.00–0.03      | Virtually zero chance of multiple_resolutions with correct coverage       |
| Rule-based baseline   | 0.08–0.15      | Gets stuck on fraud rule; misses account verification step                |
| LLM agent (GPT-4o)    | 0.38–0.50      | Usually catches fraud escalation; may miss identity verification          |
| Optimal hand-coded    | 1.00           | All 3 issues, 12 steps, all policies respected                            |

---

## Task Summary Table

| Field                       | easy_refund             | billing_dispute              | multi_issue                          |
|-----------------------------|-------------------------|------------------------------|--------------------------------------|
| `task_id`                   | easy_refund             | billing_dispute              | multi_issue                          |
| `difficulty`                | easy                    | medium                       | hard                                 |
| `max_steps`                 | 8                       | 14                           | 25                                   |
| `optimal_steps`             | 4                       | 7                            | 12                                   |
| `issue_types`               | wrong_item_received     | duplicate_charge             | account_locked, unauthorized_transaction, late_delivery |
| `ground_truth`              | refund_issued           | partial_refund_issued        | multiple_resolutions                 |
| `fraud_flag`                | false                   | false                        | true                                 |
| `applicable_policies`       | POL-REFUND-001, POL-SHIP-001 | POL-REFUND-001, POL-FRAUD-001, POL-FRAUD-002 | POL-FRAUD-001, POL-ACCT-001, POL-SHIP-001, POL-COMP-001 |
| Baseline expected score     | 0.55–0.65               | 0.28–0.38                    | 0.08–0.15                            |
| LLM agent expected score    | 0.82–0.92               | 0.60–0.72                    | 0.38–0.50                            |
| Optimal score               | 0.975                   | 0.97                         | 1.00                                 |

---

*End of TASKS.md — Version 1.0.0*