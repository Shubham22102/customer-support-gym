---
title: Customer Support Resolution Gym
emoji: 🎧
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Customer Support Resolution Gym

An OpenEnv environment for training and evaluating RL agents on complex, multi-step customer support tasks via policy compliance and database interactions.

[![PyPI version](https://badge.fury.io/py/openenv-customer-support-gym.svg)](https://badge.fury.io/py/openenv-customer-support-gym)
[![Hugging Face Spaces](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue)](https://huggingface.co/spaces/username/customer-support-gym)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

The Customer Support Resolution Gym is a simulated environment designed to benchmark LLM agents in realistic, text-based operational scenarios. Built on the OpenEnv framework, it provides a safe, reproducible sandbox where agents must resolve customer issues by invoking functional APIs, querying databases, interpreting textual policies, and managing customer sentiment over multi-turn interactions.

Customer support represents an ideal domain for measuring the real-world utility of Reinforcement Learning (RL) and agentic systems. It demands a complex blend of language comprehension, long-horizon planning, strict adherence to business rules, and the ability to execute state-mutating actions (like issuing refunds or updating records). Unlike pure coding or math benchmarks, success here requires balancing competing objectives efficiently while handling ambiguous user inputs.

This project fills a critical gap in the OpenEnv Hub ecosystem. While many existing environments focus on web navigation or pure terminal command execution, this gym focuses specifically on **API-driven business logic and policy compliance**. It challenges agents to synthesize information across structured (SQL databases, API returns) and unstructured (customer messages, policy documents) modalities to arrive at the correct resolution state.

## Quick Start

### Installation

```bash
pip install openenv-customer-support-gym
```

### Async Usage

```python
import asyncio
from customer_support_gym.client import SupportEnv, make_action
from models import ActionType

async def main():
    env = SupportEnv(url="http://localhost:8000")
    
    # Initialize a new episode
    obs = await env.reset(task_id="easy_refund")
    print(f"Customer Issue: {obs.customer_message}")
    
    # Take an action
    action = make_action(ActionType.LOOKUP_ORDER, order_id="ORD-482910")
    result = await env.step(action, episode_id=obs.episode_id)
    
    # Check updated state
    state = await env.state(obs.episode_id)
    print(f"Current Status: {state.resolution}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Sync Usage

```python
from customer_support_gym.client import SupportEnv, make_action
from models import ActionType

# Create a synchronous client
env = SupportEnv(url="http://localhost:8000").sync()

obs = env.reset(task_id="easy_refund")
action = make_action(ActionType.LOOKUP_ORDER, order_id="ORD-482910")
result = env.step(action, episode_id=obs.episode_id)
```

## Environment Description

The environment simulates the internal support portal of **ShopEasy**, a fictional e-commerce platform. Agents act as customer support representatives endowed with a specific set of tools to access company systems.

**Episode Structure**:
1. **Reset**: An episode begins when the `reset()` method is called with a specific `task_id`. The environment initializes an ephemeral SQLite database seeded with customer and order records relevant to the task and returns an initial observation containing the customer's opening message.
2. **Steps**: The agent takes sequential actions using the `step()` method. Each action can query information, mutate the database, or communicate with the customer. The environment processes the action, enforces policies, updates attributes like customer sentiment, and returns the new state.
3. **Close Ticket**: The episode concludes when the agent executes the `close_ticket` action or when the maximum step limit is reached. A final reward is calculated based on the ticket's final resolving state.

**Max Steps**:
Each task has a predefined `max_steps` limit to encourage efficiency. If the agent exceeds this limit without closing the ticket, the episode terminates automatically with a reward of 0.0.

## Action Space

The action space consists of 8 distinct tools the agent can use.

| Action | Parameters | Description | Sentiment Effect |
| :--- | :--- | :--- | :--- |
| `lookup_order` | `order_id` (str) | Retrieves detailed order information. | Neutral |
| `lookup_customer` | `customer_id` (str) | Retrieves customer profile and history. | Neutral |
| `search_kb` | `query` (str) | Searches the knowledge base for articles. | Neutral |
| `check_policy` | `policy_id` (str) | Retrieves the text of a specific policy rule. | Neutral |
| `issue_refund` | `order_id` (str), `amount` (float), `refund_type` (str), `reason` (str) | Processes a partial or full refund. | Positive |
| `cancel_order` | `order_id` (str), `reason` (str) | Cancels an active order. | Negative |
| `send_message` | `message` (str), `message_type` (str) | Sends a communication to the customer. | Varies by type |
| `close_ticket` | `resolution` (str), `summary` (str) | Finalizes the ticket and ends the episode. | Neutral |

## Observation Space

After each action, the environment returns a `SupportObservation` containing the current context.

| Field | Type | Description |
| :--- | :--- | :--- |
| `episode_id` | str | Unique identifier for the current episode. |
| `step_count` | int | Number of actions taken so far. |
| `max_steps` | int | Maximum allowed steps before termination. |
| `ticket_status` | str | Current status ('open', 'pending', 'resolved'). |
| `customer_message` | str | The most recent message from the customer. |
| `last_action_result` | str | The outcome or returned data from the previous action. |
| `available_actions` | list[str] | List of action names currently available. |
| `sentiment_score` | float | Current customer sentiment (0.0 to 1.0). |
| `system_alerts` | list[str] | Warnings or notifications from the system (e.g., policy violations). |
| `active_policies` | list[str] | IDs of policy documents currently referenced in the context. |
| `resolved_issues` | list[str] | List of issue types currently marked as resolved. |

## Reward Function

The environment relies on a sophisticated grading mechanism to evaluate agent performance over four dimensions:

**Final Formula**:
`Reward = (R * 0.55) + (E * 0.20) + (C * 0.15) + (S * 0.10)`

| Component | Weight | What it measures |
| :--- | :--- | :--- |
| **Resolution (R)** | 55% | Correctness of the final action (`close_ticket` resolution type) against the ground truth. Checks family matches and multi-issue coverage. |
| **Efficiency (E)** | 20% | Agent conciseness. Starts degrading linearly as the agent takes more steps than the `optimal_steps` defined for the task. |
| **Compliance (C)** | 15% | Adherence to business rules. Reduces proportionally based on the number of policies violated during the episode. |
| **Sentiment (S)** | 10% | Final customer sentiment score, influenced by responsiveness, tone (`send_message`), and actions taken (e.g., cancellations vs refunds). |

*Note: Intermediate steps always return a reward of `0.0`. The final calculated reward is only returned upon episode termination (done=True).*

## Tasks

### easy_refund
**Difficulty**: Easy
**Scenario**: A customer received the wrong item and requests a refund. Support must verify the order, check the refund policy, issue a full refund, and close the ticket.
**Optimal Steps**: 4
**Ground Truth**: `refund_issued`

### billing_dispute
**Difficulty**: Medium
**Scenario**: A customer disputes a duplicate charge on their recent invoice. Support must look up the customer and order, verify the duplicate billing in the database, issue a partial refund for the erroneous amount, and close the ticket.
**Optimal Steps**: 5
**Ground Truth**: `partial_refund_issued`

### multi_issue
**Difficulty**: Hard
**Scenario**: A customer reports both a late delivery and that their account appears locked. Support must investigate the order status, unlock the account, apply a courtesy credit for the delay, and assure the customer the issues are resolved.
**Optimal Steps**: 7
**Ground Truth**: `multiple_resolutions`

### Baseline Scores

| Task | Baseline Score | LLM Agent Score | Optimal Score |
| :--- | :--- | :--- | :--- |
| `easy_refund` | 0.55–0.65 | 0.82–0.92 | 0.975 |
| `billing_dispute`| 0.28–0.38 | 0.60–0.72 | 0.97 |
| `multi_issue` | 0.08–0.15 | 0.38–0.50 | 1.00 |

*(Note: Baseline is a heuristic script; LLM Agent assumes a capable model with tool-use guidance.)*

## Example Episode Trace

A flawless execution of the `easy_refund` task:

1. **reset("easy_refund")**
   * Customer: "I ordered a toaster but received a blender. I want my money back."
   * Step Count: 0
2. **step(`lookup_order`, {"order_id": "ORD-482910"})**
   * Output: `{"status": "DELIVERED", "items": [{"sku": "SKU-992", "name": "Blender", "price": 349.99}]}`
   * Step Count: 1
3. **step(`check_policy`, {"policy_id": "POL-REFUND-001"})**
   * Output: `"Full refunds are authorized for incorrect item deliveries without requiring a return..."`
   * Step Count: 2
4. **step(`issue_refund`, {"order_id": "ORD-482910", "amount": 349.99, "refund_type": "full", "reason": "Wrong item"})**
   * Output: `"Refund processed successfully."`
   * Sentiment: +0.2
   * Step Count: 3
5. **step(`close_ticket`, {"resolution": "refund_issued", "summary": "Refunded full amount for incorrect delivery."})**
   * Done: True
   * Reward: **0.975**

## Setup and Development

### Clone and Install
```bash
git clone https://github.com/username/customer-support-gym.git
cd customer-support-gym
python -m venv .venv
source .venv/bin/activate
pip install -r server/requirements.txt
```

### Run Server Locally
```bash
uvicorn server.app:app --reload --port 8000
```

### Run Baseline Agent
In a separate terminal, while the server is running:
```bash
python client.py
```

### Docker Build and Run
```bash
docker build -t customer-support-gym -f server/Dockerfile .
docker run -p 8000:8000 customer-support-gym
```

### Deploy to HF Spaces
```bash
openenv push --space username/customer-support-gym
```

## File Structure

```
customer_support_gym/
├── .openenv/                 # OpenEnv framework spec config
│   └── openenv.yaml
├── data/                     # Environment initialization data
│   ├── tickets.json          # Definitions for all 10 tasks
│   ├── policies.json         # Business rules to adhere to
│   └── knowledge_base.json   # Searchable support articles
├── server/                   # Environment Backend (FastAPI)
│   ├── app.py                # Server entrypoint and API routes
│   ├── environment.py        # SupportEnvironment orchestrator logic
│   ├── tool_router.py        # Action execution & DB mutation logic
│   ├── ticket_generator.py   # Ticket definition loader
│   ├── grader.py             # Reward function calculation
│   ├── requirements.txt      # Server dependencies
│   └── Dockerfile            # Container definition
├── tests/                    # Test suite
│   ├── test_environment.py   # Integration tests
│   └── test_grader.py        # Unit tests for scoring logic
├── models.py                 # Shared Pydantic schemas (OpenEnv compatible)
├── client.py                 # Sync/Async wrapper for `EnvClient`
├── baseline.py               # Reference heuristic agent script
├── README.md                 # This document
└── ARCHITECTURE.md           # Detailed technical design
```

## License

MIT License
