# CLAUDE.md — Customer Support Resolution Gym
## Rules for AI Coding Agents

Read this file completely before writing a single line of code.
These are hard rules. They are not suggestions. Do not interpret them.
Do not find exceptions. When in doubt, re-read the relevant rule.

---

## Step 0 — Read These Documents First

Before writing any code, read these documents in this exact order:

```
1. PRD.md           — what the environment does and why
2. DATA_SCHEMA.md   — every type, model, and enum you will use
3. ARCHITECTURE.md  — where every file lives and what it owns
4. REWARD_SPEC.md   — how grader.py must work, with worked examples
5. TASKS.md         — the three tasks with ground truth and optimal paths
```

If you have not read all five, stop and read them. Code written without
reading these documents will be wrong and will need to be deleted.

---

## 1. Tech Stack — Hard Constraints

Use exactly these technologies. No substitutions.

```
Language:       Python 3.11 (not 3.10, not 3.12)
Framework:      openenv-core          (pip install openenv-core)
API server:     FastAPI >= 0.110.0    (pip install fastapi)
ASGI server:    uvicorn[standard]     (pip install uvicorn[standard])
Data models:    pydantic >= 2.6.0     (pip install pydantic)
                USE PYDANTIC V2 SYNTAX — not v1
Database:       aiosqlite >= 0.20.0   (pip install aiosqlite)
                SQLite ONLY. One DB file per episode.
Testing:        pytest >= 8.0.0
                pytest-asyncio >= 0.23.0
                asyncio_mode = "auto" in pyproject.toml
```

**Forbidden packages — do not install or import:**
```
❌ postgres, asyncpg, psycopg2, sqlalchemy  (use aiosqlite only)
❌ redis, celery, dramatiq                  (no queues needed)
❌ langchain, llamaindex, langraph          (no LLM frameworks)
❌ openai, anthropic                        (no LLM calls in environment)
❌ gradio, streamlit, flask, django         (no UI frameworks)
❌ httpx, requests, aiohttp                 (no outbound HTTP inside environment)
❌ boto3, google-cloud-*                    (no cloud SDKs)
❌ pandas, numpy, scipy                     (no data science libs needed)
```

---

## 2. File Ownership — Strict Boundaries

Every responsibility belongs to exactly one file. These rules are absolute.

### models.py
```
OWNS:    All Pydantic models. All Enum definitions.
IMPORTS: openenv.core.models, pydantic, typing, datetime, enum
NEVER:   Business logic. Database calls. Imports from any other project file.
```

### server/environment.py
```
OWNS:    SupportEnvironment class. reset(), step(), state() methods.
         Episode lifecycle. TicketState management. Episode dict.
IMPORTS: models.py, server/ticket_generator.py, server/tool_router.py, server/grader.py
NEVER:   Tool logic. Reward computation. JSON file loading. HTTP requests. LLM calls.
```

### server/ticket_generator.py
```
OWNS:    Loading tickets.json. Parsing EpisodeConfig. Selecting by task_id.
IMPORTS: models.py, json, pathlib
NEVER:   Modifying ticket configs. Generating tickets procedurally.
         Importing from tool_router.py, grader.py, or environment.py.
```

### server/tool_router.py
```
OWNS:    Eight handler functions, one per ActionType. ToolResult dataclass.
         Sentiment delta computation. state_mutations dict. DB reads/writes.
IMPORTS: models.py, aiosqlite, uuid, datetime, json, pathlib
NEVER:   Reward computation. Importing from grader.py. HTTP requests. LLM calls.
```

### server/grader.py
```
OWNS:    Grader class. score() method. Four component functions.
         compute_resolution_score, compute_efficiency_score,
         compute_compliance_score, compute_sentiment_score.
IMPORTS: models.py ONLY
NEVER:   Database calls. Side effects. Importing from tool_router.py.
         Importing from environment.py. Modifying TicketState.
```

### server/app.py
```
OWNS:    FastAPI app factory. Route wiring. Data file loading at startup.
IMPORTS: models.py, server/environment.py, server/ticket_generator.py,
         server/tool_router.py, server/grader.py, openenv.core.env_server
NEVER:   Business logic. Model definitions. Route handlers beyond OpenEnv spec.
```

### client.py
```
OWNS:    SupportEnv(EnvClient) subclass. Two class attributes only.
IMPORTS: openenv.core.client, models.py
NEVER:   Business logic. Server-side imports. Hardcoded base_url.
```

### baseline.py
```
OWNS:    RuleBasedAgent class. main() runner. Score table printer.
IMPORTS: asyncio, client.py, models.py
NEVER:   Server-side imports (no environment.py, no grader.py, no tool_router.py).
         LLM calls. External API calls. Non-deterministic behaviour.
```

---

## 3. Coding Rules

### 3.1 Async
```python
# ALL methods in SupportEnvironment are async def. No exceptions.
async def reset(self, task_id: str) -> SupportObservation: ...
async def step(self, action: SupportAction) -> StepResult: ...
async def state(self) -> TicketState: ...

# ALL tool handlers in ToolRouter are async def.
async def _handle_lookup_order(self, ...) -> ToolResult: ...
```

### 3.2 Type hints
```python
# Every function has full type hints. No bare dict return types.

# CORRECT
async def score(self, state: TicketState, config: EpisodeConfig) -> tuple[float, dict[str, Any]]:

# WRONG — no hints
def score(self, state, config):

# WRONG — bare dict
def score(self, state: TicketState) -> dict:
```

### 3.3 Reward clamping
```python
# Always clamp rewards and sub-scores. Never skip.
reward = max(0.0, min(1.0, raw_value))

# Always use float arithmetic, never integer
score = float(numerator) / float(denominator)  # not numerator // denominator
```

### 3.4 Sentiment clamping
```python
# Always clamp sentiment after every update
state.customer_sentiment = max(0.0, min(1.0, state.customer_sentiment + delta))
```

### 3.5 Pydantic v2 syntax
```python
# CORRECT — Pydantic v2
from pydantic import BaseModel, Field, model_validator

class MyModel(BaseModel):
    value: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def check_something(self) -> "MyModel":
        ...

# WRONG — Pydantic v1 syntax
@validator("value")  # deprecated
def check_value(cls, v): ...
```

### 3.6 Database access
```python
# Use aiosqlite with async context managers
async with aiosqlite.connect(db_path) as db:
    db.row_factory = aiosqlite.Row
    async with db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)) as cursor:
        row = await cursor.fetchone()
        if row is None:
            return {"error": f"Order {order_id} not found"}
        return dict(row)
```

### 3.7 Tool result errors
```python
# CORRECT — return error as tool_result dict, never raise
return ToolResult(
    tool_result={"error": "Order ORD-999 not found"},
    sentiment_delta=0.0,
    state_mutations={},
)

# WRONG — do not raise inside tool handlers
raise ValueError("Order not found")  # this breaks the episode
```

### 3.8 Intermediate rewards
```python
# CORRECT — intermediate steps always return 0.0
if not done:
    return StepResult(observation=obs, reward=0.0, done=False, info={})

# WRONG — never return non-zero reward on intermediate step
return StepResult(observation=obs, reward=0.3, done=False, info={})
```

### 3.9 Episode isolation
```python
# CORRECT — each episode has its own DB file
db_path = Path(f"data/episodes/{episode_id}.db")

# WRONG — do not share a single DB across episodes
db_path = Path("data/shopease.db")  # shared DB breaks concurrency
```

### 3.10 String IDs
```python
# Generate IDs with uuid for episodes, uppercase hex for records
import uuid
import secrets

episode_id   = str(uuid.uuid4())
refund_id    = "REF-" + secrets.token_hex(3).upper()
escalation_id = "ESC-" + secrets.token_hex(3).upper()
```

---

## 4. What You Must Never Do

These are the ten most common mistakes. Read them before coding.

```
1. Never define a Pydantic model outside models.py
   ─ Not in tool_router.py, not in environment.py, not inline anywhere.

2. Never import grader.py from tool_router.py
   ─ These two files must never import each other.

3. Never call an external HTTP endpoint from inside the environment
   ─ No requests.get(), no httpx.get(), no aiohttp. The environment is offline.

4. Never call an LLM inside the environment
   ─ No openai.ChatCompletion, no anthropic.messages.create, nothing.
   ─ The environment must be deterministic and offline.

5. Never return reward != 0.0 on a non-terminal step
   ─ reward=0.0 on every step until done=True.

6. Never skip the reward clamp
   ─ max(0.0, min(1.0, value)) on the final reward and all sub-scores.

7. Never use a shared SQLite DB across episodes
   ─ Each episode_id gets its own DB file at data/episodes/{episode_id}.db

8. Never add ActionType values not in DATA_SCHEMA.md
   ─ There are exactly 8 action types. Adding a 9th is wrong.

9. Never raise an unhandled exception inside a tool handler
   ─ All errors return as {"error": "..."} in tool_result.

10. Never add UI code (Gradio, Streamlit, React)
    ─ The only web interface is the OpenEnv built-in at /web.
    ─ Set ENABLE_WEB_INTERFACE=true in the environment to enable it.
```

---

## 5. When You Are Uncertain

Follow this decision tree exactly:

```
Is the answer in PRD.md?
  YES → follow PRD.md
  NO  → Is the answer in DATA_SCHEMA.md?
          YES → follow DATA_SCHEMA.md
          NO  → Is the answer in ARCHITECTURE.md?
                  YES → follow ARCHITECTURE.md
                  NO  → Is the answer in REWARD_SPEC.md?
                          YES → follow REWARD_SPEC.md
                          NO  → Is the answer in TASKS.md?
                                  YES → follow TASKS.md
                                  NO  → STOP. Ask the user.
                                        Do not invent behaviour.
```

**Never invent behaviour not specified in the documents.**
If a question is not answered by any of the five documents, ask the user
rather than guessing. A wrong assumption baked into the environment takes
hours to find and fix.

---

## 6. Build Order

Build files in this exact order. Do not skip ahead. Do not build in parallel.

```
Phase 1 — Models (no logic, no DB)
  1. models.py          — copy every model from DATA_SCHEMA.md exactly
  2. Run: python -c "from models import SupportAction, SupportObservation"
     Must import without errors before proceeding.

Phase 2 — Data files
  3. data/tickets.json        — use structure from DATA_SCHEMA.md + TASKS.md
  4. data/policies.json       — use examples from DATA_SCHEMA.md Section 6
  5. data/knowledge_base.json — use examples from DATA_SCHEMA.md Section 7

Phase 3 — Server components (build and unit-test each before next)
  6. server/ticket_generator.py  — test: get_config("easy_refund") returns EpisodeConfig
  7. server/tool_router.py       — test each handler in isolation with mock state
  8. server/grader.py            — test all vectors in REWARD_SPEC.md Section 8
  9. server/environment.py       — test: reset() → step() × 4 → close_ticket()
 10. server/app.py               — test: uvicorn server starts on port 8000

Phase 4 — Client and baseline
 11. client.py     — test: SupportEnv connects to running server
 12. baseline.py   — test: prints score table, scores are reproducible

Phase 5 — Deployment
 13. server/Dockerfile   — test: docker build && docker run works
 14. openenv.yaml        — test: openenv push deploys to HF Spaces
 15. tests/              — all 4 test files pass
```

---

## 7. Testing Requirements

Every test in `tests/` must pass before submission. Zero failures allowed.

```python
# tests/test_grader.py must include these exact assertions:
assert reward == 0.975             # perfect easy_refund
assert reward == 0.0               # timeout
assert 0.0 <= reward <= 1.0        # bounds always held
assert isinstance(reward, float)   # type always float

# tests/test_tool_router.py must include:
# - lookup_order with valid order_id returns order dict
# - lookup_order with invalid order_id returns {"error": ...}
# - issue_refund on fraud_flagged order records POL-FRAUD-001 violation
# - escalate returns valid EscalationRecord shape

# tests/test_environment.py must include:
# - reset() returns SupportObservation with step_count=0
# - step() increments step_count by exactly 1
# - timeout at max_steps returns reward=0.0 and done=True
# - close_ticket returns done=True
```

---

## 8. Submission Checklist

Run this checklist before submitting. Every item must be checked.

```
[ ] python -c "from models import *" runs without errors
[ ] python baseline.py prints scores for all 3 tasks
[ ] Baseline scores are identical on two consecutive runs (reproducible)
[ ] docker build -t support-gym . succeeds
[ ] docker run -p 8000:8000 support-gym starts without errors
[ ] openenv push --repo-id <username>/customer-support-gym succeeds
[ ] baseline.py --base-url <hf_spaces_url> runs against live deployment
[ ] pytest tests/ reports 0 failures
[ ] openenv.yaml has correct base_url pointing to HF Spaces
[ ] README.md exists and contains: description, action space table,
    observation space table, reward formula, task descriptions,
    baseline score table, and one example episode trace
```

---

*End of CLAUDE.md — Version 1.0.0*
*These rules exist to save you debugging time. Follow them.*