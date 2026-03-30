from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Type

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from models import SupportAction, SupportObservation, PolicyRule, KBArticle
from server.environment import SupportEnvironment
from server.ticket_generator import TicketGenerator
from server.tool_router import ToolRouter
from server.grader import Grader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenEnv compat shim
# ---------------------------------------------------------------------------
# `openenv-core` (pip install openenv-core) is the canonical provider of
# create_app().  If it is installed we prefer it; if not, we fall back to the
# hand-rolled implementation below that mirrors the OpenEnv WebSocket protocol
# exactly: three WebSocket routes (/reset, /step, /state) plus a JSON-HTTP
# health route (/health).

try:
    from openenv.core.env_server import create_app as _openenv_create_app  # type: ignore[import]
    _OPENENV_AVAILABLE = True
except ImportError:
    _OPENENV_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data-loading helpers (pure I/O, no business logic)
# ---------------------------------------------------------------------------

def _load_policies(path: Path) -> dict[str, PolicyRule]:
    """Load policies.json and return a mapping of policy_id → PolicyRule."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_list = data.get("policies", data) if isinstance(data, dict) else data
    return {p["policy_id"]: PolicyRule(**p) for p in raw_list}


def _load_kb(path: Path) -> list[KBArticle]:
    """Load knowledge_base.json and return a list of KBArticle objects."""
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_list = data.get("articles", data) if isinstance(data, dict) else data
    return [KBArticle(**a) for a in raw_list]


# ---------------------------------------------------------------------------
# Manual OpenEnv WebSocket protocol implementation
# ---------------------------------------------------------------------------

def _make_error_response(message: str, code: str = "internal_error") -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}


def _build_openenv_app(
    env: SupportEnvironment,
    action_class: Type[SupportAction],
    observation_class: Type[SupportObservation],
) -> FastAPI:
    """
    Hand-rolled FastAPI app that implements the OpenEnv WebSocket protocol:

    WebSocket /reset
        Client sends: {"task_id": "<str>"}   (optional; defaults to "easy_refund")
        Server sends: {"type": "observation", "observation": <SupportObservation JSON>,
                        "episode_id": "<str>"}

    WebSocket /step
        Client sends: {"episode_id": "<str>", "action": <SupportAction JSON>}
        Server sends: {"type": "step_result", "observation": ...,
                        "reward": float, "done": bool, "info": {...},
                        "episode_id": "<str>"}

    WebSocket /state
        Client sends: {"episode_id": "<str>"}
        Server sends: {"type": "state", "state": {...}, "episode_id": "<str>"}

    HTTP GET /health
        Response: {"status": "ok"}
    """

    app = FastAPI(
        title="Customer Support Resolution Gym",
        description=(
            "OpenEnv-compatible multi-turn customer-support environment. "
            "Exposes /reset, /step, /state (WebSocket) and /health (HTTP)."
        ),
        version="0.1.0",
    )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/health", tags=["meta"])
    async def health() -> JSONResponse:
        """Liveness probe. Returns HTTP 200 {\"status\": \"ok\"}."""
        return JSONResponse({"status": "ok"})

    # ------------------------------------------------------------------
    # /info  – lists available task_ids (handy for debugging)
    # ------------------------------------------------------------------

    @app.get("/info", tags=["meta"])
    async def info() -> JSONResponse:
        """Return environment metadata including available task IDs."""
        return JSONResponse(
            {
                "name": "customer-support-resolution-gym",
                "version": "0.1.0",
                "action_class": action_class.__name__,
                "observation_class": observation_class.__name__,
                "task_ids": env._ticket_generator.list_task_ids(),
            }
        )

    # ------------------------------------------------------------------
    # WebSocket /reset
    # ------------------------------------------------------------------

    @app.websocket("/reset")
    async def ws_reset(websocket: WebSocket) -> None:
        """
        Reset the environment and start a new episode.

        Receive (JSON):
            {"task_id": "easy_refund"}   # task_id is optional

        Send (JSON) on success:
            {
                "type": "observation",
                "episode_id": "<uuid>",
                "observation": { ...SupportObservation fields... }
            }

        Send (JSON) on error:
            {"type": "error", "code": "<code>", "message": "<detail>"}
        """
        await websocket.accept()
        try:
            raw: dict[str, Any] = await websocket.receive_json()
            task_id: str = raw.get("task_id", "easy_refund")

            observation: SupportObservation = await env.reset(task_id=task_id)

            await websocket.send_json(
                {
                    "type": "observation",
                    "episode_id": observation.episode_id,
                    "observation": observation.model_dump(mode="json"),
                }
            )
        except (ValueError, KeyError) as exc:
            logger.exception("reset: invalid request")
            await websocket.send_json(
                _make_error_response(str(exc), code="invalid_request")
            )
        except Exception as exc:
            logger.exception("reset: unexpected error")
            await websocket.send_json(_make_error_response(str(exc)))
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # WebSocket /step
    # ------------------------------------------------------------------

    @app.websocket("/step")
    async def ws_step(websocket: WebSocket) -> None:
        """
        Execute a single agent action within an existing episode.

        Receive (JSON):
            {
                "episode_id": "<uuid>",
                "action": { "action_type": "lookup_order", "parameters": {...} }
            }

        Send (JSON) on success:
            {
                "type": "step_result",
                "episode_id": "<uuid>",
                "observation": { ...SupportObservation fields... },
                "reward": 0.0,
                "done": false,
                "info": {}
            }

        Send (JSON) on error:
            {"type": "error", "code": "<code>", "message": "<detail>"}
        """
        await websocket.accept()
        try:
            raw: dict[str, Any] = await websocket.receive_json()

            episode_id: str = raw["episode_id"]
            action_data: dict[str, Any] = raw["action"]

            # Validate action via Pydantic
            try:
                action = action_class.model_validate(action_data)
            except ValidationError as exc:
                await websocket.send_json(
                    _make_error_response(
                        f"Action validation failed: {exc}",
                        code="validation_error",
                    )
                )
                return

            # Delegate to the environment
            step_result = await env.step(action=action, episode_id=episode_id)

            await websocket.send_json(
                {
                    "type": "step_result",
                    "episode_id": episode_id,
                    "observation": step_result.observation.model_dump(mode="json"),
                    "reward": step_result.reward,
                    "done": step_result.done,
                    "info": step_result.info,
                }
            )
        except KeyError as exc:
            logger.exception("step: missing required field")
            await websocket.send_json(
                _make_error_response(
                    f"Missing required field: {exc}", code="invalid_request"
                )
            )
        except Exception as exc:
            logger.exception("step: unexpected error")
            await websocket.send_json(_make_error_response(str(exc)))
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # WebSocket /state
    # ------------------------------------------------------------------

    @app.websocket("/state")
    async def ws_state(websocket: WebSocket) -> None:
        """
        Return a read-only snapshot of an active episode's internal state.

        Receive (JSON):
            {"episode_id": "<uuid>"}

        Send (JSON) on success:
            {
                "type": "state",
                "episode_id": "<uuid>",
                "state": { ...TicketState fields serialized... }
            }

        Send (JSON) on error:
            {"type": "error", "code": "<code>", "message": "<detail>"}
        """
        await websocket.accept()
        try:
            raw: dict[str, Any] = await websocket.receive_json()
            episode_id: str = raw["episode_id"]

            state_dict: dict[str, Any] = await env.state(episode_id=episode_id)

            if "error" in state_dict:
                await websocket.send_json(
                    _make_error_response(state_dict["error"], code="not_found")
                )
            else:
                await websocket.send_json(
                    {
                        "type": "state",
                        "episode_id": episode_id,
                        "state": state_dict,
                    }
                )
        except KeyError as exc:
            logger.exception("state: missing required field")
            await websocket.send_json(
                _make_error_response(
                    f"Missing required field: {exc}", code="invalid_request"
                )
            )
        except Exception as exc:
            logger.exception("state: unexpected error")
            await websocket.send_json(_make_error_response(str(exc)))
        finally:
            try:
                await websocket.close()
            except Exception:
                pass

    return app


# ---------------------------------------------------------------------------
# create_app — public entry point (mirrors openenv.core.env_server.create_app)
# ---------------------------------------------------------------------------

def create_app(
    env: SupportEnvironment,
    action_class: Type[SupportAction],
    observation_class: Type[SupportObservation],
) -> FastAPI:
    """
    Build and return the FastAPI application.

    Prefers the official ``openenv-core`` implementation when installed;
    falls back to the hand-rolled WebSocket implementation above if the
    package is unavailable.

    Parameters
    ----------
    env:
        A fully-initialised :class:`SupportEnvironment` instance.
    action_class:
        The :class:`SupportAction` Pydantic model class.
    observation_class:
        The :class:`SupportObservation` Pydantic model class.

    Returns
    -------
    FastAPI
        A configured application ready to pass to ``uvicorn.run()``.
    """
    if _OPENENV_AVAILABLE:
        logger.info("openenv-core detected — using official create_app()")
        return _openenv_create_app(env, action_class, observation_class)

    logger.info(
        "openenv-core not installed — using built-in WebSocket protocol implementation"
    )
    return _build_openenv_app(env, action_class, observation_class)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_support_app() -> FastAPI:
    """
    Construct the fully-wired Customer Support Gym FastAPI application.

    Loads ``data/policies.json`` and ``data/knowledge_base.json`` exactly
    once at startup, builds all server-side components, and wires the
    OpenEnv routes.

    Returns
    -------
    FastAPI
        The application instance.  Uvicorn should point at
        ``server.app:app``.
    """
    base = Path(__file__).parent.parent  # project root

    ticket_gen = TicketGenerator(base / "data" / "tickets.json")
    policies = _load_policies(base / "data" / "policies.json")
    kb = _load_kb(base / "data" / "knowledge_base.json")

    grader = Grader()
    router = ToolRouter(policies=policies, kb_articles=kb)
    env = SupportEnvironment(
        ticket_generator=ticket_gen,
        tool_router=router,
        grader=grader,
        episodes_dir=base / "data" / "episodes",
    )

    application = create_app(env, SupportAction, SupportObservation)
    return application


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn server.app:app)
# ---------------------------------------------------------------------------

app: FastAPI = create_support_app()
