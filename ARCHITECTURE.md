# ARCHITECTURE.md — Customer Support Resolution Gym
## System Design and File Ownership Specification

**Version:** 1.0.0
**Authority:** This document governs folder structure, file responsibilities,
import boundaries, and data flow. Read this after PRD.md and DATA_SCHEMA.md.
**Rule for AI coding agents:** Every file you create must appear in this
document. Do not create files not listed here. Do not move responsibilities
between files.

---

## 1. Complete Folder and File Tree

```
customer_support_gym/
│
├── CLAUDE.md                    ← AI agent rules. Read before any coding.
├── PRD.md                       ← Product requirements. The "what and why".
├── ARCHITECTURE.md              ← This file. Structure and ownership.
├── DATA_SCHEMA.md               ← All models, enums, JSON schemas.
├── REWARD_SPEC.md               ← Reward formula and grader specification.
├── TASKS.md                     ← Three task configs with ground truth.
│
├── openenv.yaml                 ← OpenEnv Hub manifest. Required for deployment.
├── pyproject.toml               ← Package dependencies and metadata.
├── __init__.py                  ← Package exports. Three lines only.
│
├── models.py                    ← ALL Pydantic models and enums. Nothing else.
├── client.py                    ← EnvClient subclass. No business logic.
├── baseline.py                  ← Standalone rule-based agent + scorer.
│
├── data/
│   ├── tickets.json             ← 20 episode configs with db_seed records.
│   ├── policies.json            ← 10 PolicyRule objects.
│   ├── knowledge_base.json      ← 15+ KBArticle objects.
│   └── episodes/                ← Runtime SQLite DBs. Created on reset().
│       └── .gitkeep             ← Keep folder in git. DB files are gitignored.
│
├── server/
│   ├── Dockerfile               ← Container definition. Single-stage build.
│   ├── requirements.txt         ← Python deps for Docker (no dev deps).
│   ├── app.py                   ← FastAPI app factory. Wires routes only.
│   ├── environment.py           ← SupportEnvironment. Orchestrator only.
│   ├── ticket_generator.py      ← Loads and validates EpisodeConfig from JSON.
│   ├── tool_router.py           ← Maps ActionType → handler. Returns raw results.
│   └── grader.py                ← Reward computation only. Pure function.
│
└── tests/
    ├── __init__.py
    ├── test_models.py            ← Pydantic validation tests.
    ├── test_tool_router.py       ← Each tool handler tested in isolation.
    ├── test_grader.py            ← Reward formula tested against known inputs.
    └── test_environment.py      ← Full reset→step→close loop tests.
```

---

## 2. File-by-File Ownership

Each entry states: what the file owns, what it is allowed to import, and what
it must never do.

---

### `models.py`

**Owns:** Every Pydantic model, every enum, every type alias used in this project.

**Allowed imports:**
```python
from __future__ import annotations
from enum import Enum
from typing import Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from openenv.core.models import Action, Observation
```

**Must never:**
- Contain any business logic (no if/else on domain rules)
- Import from any other file in this project
- Make database calls
- Contain constants that are not type definitions

---

### `server/environment.py`

**Owns:** The `SupportEnvironment` class that implements the OpenEnv
`Environment` base class. It is the orchestrator: it calls
`ticket_generator`, `tool_router`, and `grader` in the correct order, manages
`TicketState`, and constructs `SupportObservation` objects.

**Allowed imports:**
```python
import uuid
import asyncio
import aiosqlite
from datetime import datetime, timezone
from openenv.core.environment import Environment
from models import (
    SupportAction, SupportObservation, TicketState,
    EpisodeConfig, TicketStatus, ActionType, ResolutionType,
)
from server.ticket_generator import TicketGenerator
from server.tool_router import ToolRouter
from server.grader import Grader
```

**Must never:**
- Implement tool logic (no order lookups, no refund logic here)
- Compute reward values directly (always delegates to `grader.py`)
- Load JSON files directly (delegates to `ticket_generator.py`)
- Make HTTP requests
- Call an LLM

---

### `server/ticket_generator.py`

**Owns:** Loading `data/tickets.json`, validating each ticket against the
`EpisodeConfig` schema, and selecting the correct config for a given `task_id`.

**Allowed imports:**
```python
import json
from pathlib import Path
from models import EpisodeConfig, DBSeed, CustomerRecord, OrderRecord, ProductRecord
```

**Must never:**
- Modify ticket configs at runtime
- Generate tickets procedurally (all tickets are pre-authored in JSON)
- Import from `tool_router.py`, `grader.py`, or `environment.py`

**Key method signature:**
```python
class TicketGenerator:
    def __init__(self, tickets_path: Path) -> None: ...
    def get_config(self, task_id: str) -> EpisodeConfig: ...
    def list_task_ids(self) -> list[str]: ...
```

---

### `server/tool_router.py`

**Owns:** One handler function per `ActionType`. Each handler receives a
`SupportAction`, the current `TicketState`, and an open `aiosqlite.Connection`.
It executes the action, mutates `TicketState` where appropriate, and returns a
raw result dict. It also returns a `sentiment_delta: float` for the environment
to apply.

**Allowed imports:**
```python
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
import aiosqlite
from models import (
    SupportAction, TicketState, ActionType,
    RefundRecord, EscalationRecord,
    OrderRecord, CustomerRecord,
    InfoType, MessageType, EscalationReason, EscalationTeam,
    RefundType, ResolutionType,
)
```

**Must never:**
- Compute reward values (not its job — that is `grader.py`)
- Import from `grader.py`
- Load `tickets.json` or `policies.json` directly
  (policies are loaded once at startup and passed in as a dict)
- Make HTTP requests

**Handler return contract:**
```python
# Every handler returns this shape. No exceptions.
@dataclass
class ToolResult:
    tool_result: dict[str, Any]   # goes into SupportObservation.tool_result
    sentiment_delta: float         # applied to TicketState.customer_sentiment
    state_mutations: dict[str, Any]  # fields to set on TicketState after the call
```

**Router method signature:**
```python
class ToolRouter:
    def __init__(self, policies: dict[str, PolicyRule], kb_articles: list[KBArticle]) -> None: ...

    async def execute(
        self,
        action: SupportAction,
        state: TicketState,
        db: aiosqlite.Connection,
        episode_config: EpisodeConfig,
    ) -> ToolResult: ...
```

---

### `server/grader.py`

**Owns:** The `Grader` class with a single public method `score()`. Given a
completed `TicketState` and the `EpisodeConfig` (which contains ground truth),
it computes and returns the final reward float and the reward breakdown dict.
This is a pure function — no side effects, no DB calls.

**Allowed imports:**
```python
from models import TicketState, EpisodeConfig, ResolutionType, ActionType
```

**Must never:**
- Import from `tool_router.py`
- Import from `environment.py`
- Make any database calls
- Have any side effects (no writing to state, no logging with side effects)

**Key method signature:**
```python
class Grader:
    def score(
        self,
        state: TicketState,
        config: EpisodeConfig,
    ) -> tuple[float, dict[str, Any]]:
        """
        Returns (final_reward, breakdown_dict).
        final_reward is always float in [0.0, 1.0].
        breakdown_dict shape defined in DATA_SCHEMA.md Section 2.3.
        Only call this when done=True via close_ticket.
        """
        ...
```

---

### `server/app.py`

**Owns:** Creating and configuring the FastAPI application. Wiring OpenEnv
routes. Loading data files once at startup. Injecting the environment instance.

**Allowed imports:**
```python
import json
from pathlib import Path
from openenv.core.env_server import create_app
from models import SupportAction, SupportObservation
from server.environment import SupportEnvironment
from server.ticket_generator import TicketGenerator
from server.tool_router import ToolRouter
from server.grader import Grader
```

**Must never:**
- Contain business logic
- Define routes beyond what `create_app` requires
- Contain model definitions

**App factory pattern:**
```python
def create_support_app() -> FastAPI:
    tickets_path = Path("data/tickets.json")
    policies_path = Path("data/policies.json")
    kb_path = Path("data/knowledge_base.json")

    ticket_gen = TicketGenerator(tickets_path)
    grader = Grader()
    router = ToolRouter(
        policies=_load_policies(policies_path),
        kb_articles=_load_kb(kb_path),
    )
    env = SupportEnvironment(
        ticket_generator=ticket_gen,
        tool_router=router,
        grader=grader,
    )
    app = create_app(env, SupportAction, SupportObservation)
    return app

app = create_support_app()
```

---

### `client.py`

**Owns:** `SupportEnv`, the `EnvClient` subclass that end users and the
baseline agent use to connect to a running environment server.

**Allowed imports:**
```python
from openenv.core.client import EnvClient
from models import SupportAction, SupportObservation, ActionType, ResolutionType
```

**Must never:**
- Contain business logic
- Import from `server/` — the client and server are separate packages
- Hardcode a base_url

**Class signature:**
```python
class SupportEnv(EnvClient):
    action_type = SupportAction
    observation_type = SupportObservation

    # Inherits: reset(), step(), state(), sync(), __aenter__, __aexit__
```

---

### `baseline.py`

**Owns:** A standalone, executable script that runs a rule-based agent against
all three tasks and prints a score table to stdout. No imports from `server/`.

**Allowed imports:**
```python
import asyncio
import argparse
from client import SupportEnv
from models import SupportAction, ActionType, ResolutionType, InfoType, MessageType
```

**Must never:**
- Import from `server/environment.py` or `server/grader.py`
- Require a GPU or LLM to run
- Have a non-deterministic baseline score (scores must be reproducible)

**Required stdout format:**
```
Customer Support Resolution Gym — Baseline Scores
==================================================
Task              Score    Steps    Result
easy_refund       0.74     4/8      refund_issued
billing_dispute   0.31     9/14     partial_refund_issued
multi_issue       0.09     25/25    timeout
--------------------------------------------------
Mean score:       0.38
```

---

### `__init__.py`

**Owns:** Package-level exports. Exactly three lines of imports.

```python
from .models import SupportAction, SupportObservation
from .client import SupportEnv
```

---

### `openenv.yaml`

**Owns:** The OpenEnv Hub manifest. Read by the `openenv push` CLI and by
Hub discovery tooling.

```yaml
name: customer-support-resolution-gym
version: 0.1.0
description: >
  Multi-turn, tool-using customer support agent environment.
  An agent resolves e-commerce support tickets by calling structured
  tools across 5–20 step episodes. Three difficulty levels with
  dense partial reward signals.
action_class: models.SupportAction
observation_class: models.SupportObservation
base_url: "https://YOUR_HF_USERNAME-customer-support-gym.hf.space"
is_concurrent: true
tasks:
  - id: easy_refund
    difficulty: easy
    max_steps: 8
    description: "Straightforward wrong-item refund. Optimal path is 4 steps."
  - id: billing_dispute
    difficulty: medium
    max_steps: 14
    description: "Partial refund for duplicate charge. Requires order investigation."
  - id: multi_issue
    difficulty: hard
    max_steps: 25
    description: "Three simultaneous issues. Mandatory fraud escalation path."
tags:
  - customer-support
  - tool-use
  - multi-turn
  - agentic
  - rl-training
```

---

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "customer-support-gym"
version = "0.1.0"
description = "OpenEnv customer support resolution environment"
requires-python = ">=3.11"
dependencies = [
    "openenv-core",
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.6.0",
    "aiosqlite>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[tool.setuptools.packages.find]
where = ["."]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

### `server/requirements.txt`

Used by Docker only. Pin all versions.

```
openenv-core
fastapi==0.110.0
uvicorn[standard]==0.29.0
pydantic==2.6.4
aiosqlite==0.20.0
```

---

### `server/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/episodes

EXPOSE 8000

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3. Data Flow Diagram

```
CLIENT                          SERVER
──────                          ──────

SupportEnv.reset(task_id)
    │
    ▼ WebSocket /reset
                                app.py
                                  │
                                  ▼
                                environment.py :: reset()
                                  │
                                  ├─► ticket_generator.py
                                  │     └─ load EpisodeConfig from tickets.json
                                  │
                                  ├─► _seed_database(episode_id, config)
                                  │     └─ create SQLite DB at data/episodes/{id}.db
                                  │
                                  ├─► TicketState(episode_id, task_id, ...)
                                  │
                                  └─► SupportObservation(opening_message, ...)
                                          │
    ◄─────────────────────────────────────┘
SupportObservation returned


SupportEnv.step(SupportAction)
    │
    ▼ WebSocket /step
                                app.py
                                  │
                                  ▼
                                environment.py :: step()
                                  │
                                  ├─► validate action params
                                  │
                                  ├─► tool_router.execute(action, state, db, config)
                                  │     └─ handler mutates TicketState
                                  │     └─ returns ToolResult(tool_result, sentiment_delta, mutations)
                                  │
                                  ├─► apply sentiment_delta to state.customer_sentiment
                                  ├─► apply state_mutations to TicketState
                                  ├─► increment step_count
                                  ├─► compute available_actions
                                  │
                                  ├─► if done:
                                  │     └─► grader.score(state, config)
                                  │           └─ returns (reward, breakdown)
                                  │
                                  └─► StepResult(observation, reward, done, info)
                                          │
    ◄─────────────────────────────────────┘
StepResult returned
```

---

## 4. OpenEnv Component Mapping

| OpenEnv Requirement         | This Project                              | File                      |
|-----------------------------|-------------------------------------------|---------------------------|
| `Action` subclass           | `SupportAction`                           | `models.py`               |
| `Observation` subclass      | `SupportObservation`                      | `models.py`               |
| `Environment` subclass      | `SupportEnvironment`                      | `server/environment.py`   |
| `Environment.reset()`       | `SupportEnvironment.reset()`              | `server/environment.py`   |
| `Environment.step()`        | `SupportEnvironment.step()`               | `server/environment.py`   |
| `Environment.state()`       | `SupportEnvironment.state()`              | `server/environment.py`   |
| `EnvClient` subclass        | `SupportEnv`                              | `client.py`               |
| FastAPI app                 | `create_support_app()`                    | `server/app.py`           |
| `openenv.yaml`              | root `openenv.yaml`                       | `openenv.yaml`            |
| Baseline agent              | `RuleBasedAgent` in `baseline.py`         | `baseline.py`             |
| Docker container            | single-stage Python 3.11 image            | `server/Dockerfile`       |

---

## 5. Concurrency Model

Each call to `reset()` creates a fully isolated episode:

```
reset(task_id="easy_refund")
  └─ generates episode_id = uuid4()
  └─ creates data/episodes/{episode_id}.db  ← isolated SQLite per episode
  └─ stores TicketState in memory dict: self._episodes[episode_id]

step(action)  ← must pass episode_id in session context
  └─ looks up self._episodes[episode_id]
  └─ opens data/episodes/{episode_id}.db
  └─ mutates only that episode's state and DB

state()
  └─ reads self._episodes[episode_id] (read-only)
```

The in-memory `_episodes` dict is keyed by `episode_id`. Episodes are cleaned
up (DB file deleted, dict entry removed) when `done=True` is returned.

No global mutable state exists outside of `self._episodes`. This makes the
environment safe for parallel RL training workers.

---

## 6. Error Handling Contract

All errors from tool handlers return a structured dict — never raise exceptions
that reach the client.

```python
# Good — tool handler returns error as tool_result
return ToolResult(
    tool_result={"error": "Order ORD-999999 not found"},
    sentiment_delta=0.0,
    state_mutations={},
)

# Bad — never do this inside a tool handler
raise ValueError("Order not found")
```

Exceptions that escape `environment.py` are caught by the OpenEnv base class
and returned as HTTP 500 responses. The episode is considered broken; the
client must call `reset()` again.

Validation errors (wrong parameter types, missing required fields) are caught
in `tool_router.py` before calling the handler and returned as:
```python
{"error": "Validation error: parameter 'order_id' is required for action 'lookup_order'"}
```

The step is still counted when a validation error occurs.

---

## 7. Gitignore Additions

Add these to `.gitignore`:

```gitignore
# Episode databases (created at runtime)
data/episodes/*.db

# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.venv/
venv/

# Environment
.env
```

---

*End of ARCHITECTURE.md — Version 1.0.0*