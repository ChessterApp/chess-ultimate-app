"""Hermes Chess Coach — FastAPI server.

Exposes an OpenAI-compatible /v1/chat/completions endpoint
backed by Hermes AIAgent with the chess coach persona.
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
import asyncio

import chess
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import asynccontextmanager
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.config import (
    load_env,
    load_profile_config,
    load_soul,
    get_port,
    get_model_config,
    get_api_key,
    fallback_model_for,
    quick_model,
    PROFILE_DIR,
)
# load_env() must run before importing src.sessions: the global session store
# reads SUPABASE_* at import time, and without the .env loaded persistence
# silently degrades to in-memory (sessions would not survive restarts).
load_env()

from src.middleware.response_envelope import (  # noqa: E402
    extract_board_actions,
    tool_board_actions,
    wrap_response,
)
from src.middleware.rate_limiter import (  # noqa: E402
    enforce_rate_limit,
    rate_limiter,
    voice_token_rate_limiter,
    voice_tool_rate_limiter,
    get_user_tier,
    DEFAULT_TIER,
)
from src.middleware.circuit_breaker import stockfish_circuit, supabase_circuit
from src.model_router import route_model, explain_route
from src.prompt_builder import (
    attach_turn_context,
    build_system_prompt,
    build_voice_prompt,
    engine_note_block,
    hypothetical_block,
    conversation_language,
    language_note,
    review_block,
    get_prompt_version,
)
from src.event_logger import log_event, new_turn_id
from src.coach_feedback import upsert_feedback, delete_feedback
from src.identity import current_user_id
from src import config
from src import coach_diagnostics as diag
from src.processors.text_normalize import normalize_text
from src.sessions import session_store
from src.user_profile import load_user_profile, save_user_profile, UserProfile
from src.cost_monitor import (
    cost_monitor,
    record_openrouter_usage,
    record_voice_event,
    record_voice_usage,
)
from src.analytics import analytics_tracker
from src.analytics_db import compute_user_analytics, get_admin_analytics_cached
from src.retention import retention_loop
from src.billing import (
    create_checkout_session,
    get_subscription_status,
    handle_webhook_event,
    verify_whop_signature,
)
from src.voice_metrics import (
    MAX_BODY_BYTES,
    beacon_to_event,
    record_metric,
    sanitize_metric,
)
from src.voice_quota import voice_quota_ledger
from src.voice_engine_note import engine_note
from src.board_markup import MarkupFilter, strip_markup, prune_arrows

# Set HERMES_HOME so the agent picks up the chess coach profile
os.environ.setdefault("HERMES_HOME", str(PROFILE_DIR))

# Structured logging
logger = logging.getLogger("hermes.server")

# Discover and register chess tools with the Hermes tool registry
from src.tools import discover_and_register
_loaded_tools = discover_and_register()
logger.info("Registered %d chess tool modules", len(_loaded_tools))


def _maybe_discover_mcp_tools() -> list[str]:
    """Flag-gated: register external MCP-server tools into the shared registry.

    When ``COACH_MCP_ENABLED`` is true, invoke the Hermes framework's
    ``discover_mcp_tools()`` (it reads ``mcp_servers`` from
    ``~/.hermes/config.yaml`` and registers each server's tools under an
    ``mcp-<name>`` toolset in the same registry the native tools use).

    Guarded so a failed MCP connect — bad config, unreachable server, missing
    ``mcp`` package — can NEVER crash Hermes startup: on any error we log and
    continue with native tools only. Returns the registered MCP tool names
    (empty when the flag is off or discovery fails). The flag is read via the
    config module so it reflects the current environment.
    """
    if not config.COACH_MCP_ENABLED:
        return []
    try:
        from tools.mcp_tool import discover_mcp_tools

        mcp_tools = discover_mcp_tools()
        logger.info(
            "Registered %d MCP tool(s) from configured servers", len(mcp_tools)
        )
        return mcp_tools
    except Exception as exc:
        logger.exception(
            "MCP tool discovery failed — continuing with native tools only"
        )
        diag.record(
            "mcp_discovery_failed",
            level="warning",
            message="MCP tool discovery failed; running with native tools only",
            exc=exc,
        )
        return []


_loaded_mcp_tools = _maybe_discover_mcp_tools()

# Server start time for uptime tracking
_start_time = time.time()


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[Message]
    model: Optional[str] = None
    session_id: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: Message
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage = Field(default_factory=Usage)
    board_actions: list[Any] = Field(default_factory=list)


# Module-level config (loaded at import time)
_config = load_profile_config()
_model_config = get_model_config(_config)
_soul_content = load_soul()


@asynccontextmanager
def _warm_up() -> None:
    """Load at startup what the first questions after a restart used to load.

    Bench 2026-09-29: the first three turns built their agent in 1.1-2.0 s
    (then 0.03 s) and waited 1.1-2.0 s for the engine line — the framework's
    tools, the Stockfish processes and the ECO book index all load on first use.
    """
    started = time.monotonic()
    steps = {}
    try:
        _create_agent(quick_model(), "warm-up", session_id="warm-up", user_query="warm-up")
        steps["agent"] = int((time.monotonic() - started) * 1000)
    except Exception:  # noqa: BLE001 — warming up is best-effort
        logger.warning("warm-up: agent failed", exc_info=True)
    try:
        from src.voice_engine_note import engine_note

        # After 1.e4 e5: the engine, the threat search and the ECO book index.
        engine_note("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", movetime_ms=200)
        steps["engine"] = int((time.monotonic() - started) * 1000)
    except Exception:  # noqa: BLE001
        logger.warning("warm-up: engine failed", exc_info=True)
    try:
        from src.knowledge_base import load_topics
        from src.llm_transport import shared_http

        load_topics()
        shared_http()
    except Exception:  # noqa: BLE001
        logger.warning("warm-up: knowledge base failed", exc_info=True)
    _timings_log.info("warm-up done %s", json.dumps({**steps, "total": int((time.monotonic() - started) * 1000)}))


async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    app.state.config = _config
    app.state.model_config = _model_config
    app.state.soul_content = _soul_content
    # Every turn holds one executor thread for the whole agent call (5–40 s)
    # and one for the reaction; the default pool (cpu+4, 6–8 on the host)
    # queued the session/profile steps of the next students invisibly.
    asyncio.get_running_loop().set_default_executor(
        ThreadPoolExecutor(max_workers=config.COACH_EXECUTOR_THREADS, thread_name_prefix="coach")
    )
    if config.COACH_WARMUP:
        # In the background: the server takes requests at once.
        asyncio.get_running_loop().run_in_executor(None, _warm_up)

    # Daily retention purge (coach_events/analytics_events + local spool).
    # Fire-and-forget background task; kill-switch is RETENTION_ENABLED.
    retention_task = asyncio.create_task(retention_loop())
    app.state.retention_task = retention_task

    try:
        yield
    finally:
        retention_task.cancel()
        try:
            await retention_task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(title="Hermes Chess Coach", version="1.0.0", lifespan=lifespan)

# Voice tool bridge — exposes the chess tool registry to the Gemini Live coach.
from src.tool_bridge import router as tool_bridge_router
app.include_router(tool_bridge_router)


# ── Request ID middleware ──────────────────────────────────────────────


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a unique request ID to every request for tracing."""
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex[:12])
    request.state.request_id = request_id

    # Student identity for tool handlers (see src/identity.py): the text path
    # runs tools inside AIAgent, which never sees the request, so expose the
    # authenticated id via a context var for the duration of the request.
    identity_token = current_user_id.set(
        request.headers.get("x-user-id") or request.headers.get("x-clerk-user-id") or ""
    )

    logger.info(
        "request_start method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        request_id,
    )

    start = time.monotonic()
    try:
        response = await call_next(request)
    finally:
        current_user_id.reset(identity_token)
    elapsed = round((time.monotonic() - start) * 1000, 2)

    response.headers["X-Request-Id"] = request_id
    logger.info(
        "request_end path=%s status=%d duration_ms=%.2f request_id=%s",
        request.url.path,
        response.status_code,
        elapsed,
        request_id,
    )
    if response.status_code >= 400:
        diag.record(
            "http_error",
            request_id=request_id,
            level="warning" if response.status_code < 500 else "error",
            message=f"{request.method} {request.url.path} -> {response.status_code}",
            path=request.url.path,
            method=request.method,
            status=response.status_code,
            duration_ms=elapsed,
        )
    return response


def _bearer_token(request: Request) -> str:
    return request.headers.get("authorization", "").removeprefix("Bearer ").strip()


def _is_admin_request(request: Request) -> bool:
    """True when the caller asks for admin scope AND proves it with a secret.

    Admin scope (analytics across all users) is granted only to a bearer token
    matching HERMES_ADMIN_TOKEN or, failing that, the internal HERMES_API_KEY.
    A bare ``x-admin: true`` header — which any client can send — is never
    enough. With neither secret configured admin scope is unavailable.
    """
    import secrets

    if request.headers.get("x-admin") != "true":
        return False
    token = _bearer_token(request)
    if not token:
        return False
    for expected in (os.environ.get("HERMES_ADMIN_TOKEN", ""), get_api_key()):
        if expected and secrets.compare_digest(token, expected):
            return True
    return False


def _verify_api_key(request: Request) -> None:
    """Check the Authorization header against HERMES_API_KEY."""
    expected = get_api_key()
    if not expected:
        return  # No key configured = open access
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _clean_user_text(text: str) -> str:
    """NFKC-normalize inbound free-text when COACH_NORMALIZE_INPUT is enabled.

    Off by default (byte-identical passthrough). Applied only to free-text user
    messages — never to FEN/PGN or tool args. Read via the config module so the
    flag can be toggled at runtime.
    """
    if config.COACH_NORMALIZE_INPUT:
        return normalize_text(text)
    return text


def _resolve_model(requested_model: Optional[str], user_message: str = "") -> str:
    """Resolve the model to use based on request and config tiers."""
    if not requested_model:
        # Auto-route based on query complexity
        tiers = _model_config.get("tiers", {})
        return route_model(user_message, tiers, _model_config["default"])
    tiers = _model_config.get("tiers", {})
    if requested_model in tiers:
        return tiers[requested_model]
    return requested_model


def _model_gets_prompt_cache(model: str) -> bool:
    """True for models the framework applies explicit cache_control to (Claude)."""
    return "claude" in (model or "").lower()


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _skip_compression_check(agent_cls) -> None:
    """The framework's construction-time check of the compression model's context
    window downloads the models.dev registry (5 MB, ~1–2 s) once an hour — and,
    when that host is unreachable, on EVERY agent construction with a 15 s
    timeout (a failed fetch sets no TTL). The coach builds a fresh agent per
    turn and hands it one message, so context compression never runs: the
    check is a warning about a path the coach does not take."""
    if getattr(agent_cls, "_coach_compression_check_skipped", False):
        return
    agent_cls._check_compression_model_feasibility = lambda self: None
    agent_cls._coach_compression_check_skipped = True


def _create_agent(
    model: str,
    system_prompt: str,
    session_id: Optional[str] = None,
    user_query: Optional[str] = None,
    mode: str = "full",
    fallback_model: Optional[str] = None,
):
    """Create a Hermes AIAgent configured for chess coaching.

    When ``COACH_TOOL_SUBSET`` is enabled and a ``user_query`` is provided, the
    agent's tool schemas are reduced to a query-relevant subset (mirroring the
    voice path). With the flag off or ``user_query`` None the agent is left
    untouched, so behavior is byte-identical to today.

    ``fallback_model`` (an OpenRouter id) arms the framework's own failover:
    on a 429/402 from the primary it switches immediately, on other errors
    after its retries, and finishes the same turn on the fallback. The agent
    then reports the model that actually answered in ``agent.model``.
    """
    from run_agent import AIAgent

    _skip_compression_check(AIAgent)
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    agent_kwargs = dict(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        provider="openrouter",
        ephemeral_system_prompt=system_prompt,
        session_id=session_id,
        max_iterations=5,
        tool_delay=0,
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        persist_session=False,
        enabled_toolsets=["safe", "chess"],
    )
    if fallback_model and fallback_model != model:
        agent_kwargs["fallback_model"] = {
            "provider": "openrouter",
            "model": fallback_model,
            "api_key": api_key,
            "base_url": OPENROUTER_BASE_URL,
        }
    reasoning = _reasoning_config(model)
    if reasoning is not None:
        agent_kwargs["reasoning_config"] = reasoning
    if config.COACH_PROVIDER_SORT:
        agent_kwargs["provider_sort"] = config.COACH_PROVIDER_SORT
    agent = AIAgent(**agent_kwargs)
    _arm_gemini_reasoning(agent)
    _watch_stream_cuts(agent)
    # One pooled connection to OpenRouter, and a stalled first call raced
    # against the fallback model (src/llm_transport.py).
    from src import llm_transport

    llm_transport.install(agent)

    # Claude via OpenRouter gets cache_control breakpoints from the framework;
    # the tool block is part of the cached prefix, so a per-turn tool subset
    # would bust the cache on every turn and cost more than it saves. Keep the
    # full, stable tool set for those models and subset only the others.
    subset_ok = not _model_gets_prompt_cache(model)
    if config.COACH_TOOL_SUBSET and subset_ok and user_query and getattr(agent, "tools", None):
        from src.opening_knowledge import mentions_opening
        from src.tool_selector import select_openai_tool_subset

        all_tools = agent.tools
        agent.tools = select_openai_tool_subset(
            agent.tools,
            user_query,
            topk=config.COACH_TOOL_SUBSET_TOPK,
            mode=mode,
        )
        # A named opening keeps the book tools: «против жареной печени» matched
        # none of their keywords and the model answered from memory (2026-09-30).
        if mentions_opening(user_query):
            chosen = {t["function"]["name"] for t in agent.tools}
            agent.tools = agent.tools + [
                t for t in all_tools
                if t["function"]["name"] in ("get_opening_stats", "identify_opening")
                and t["function"]["name"] not in chosen
            ]
        # Keep the model-call validator consistent with the reduced tool set.
        agent.valid_tool_names = {t["function"]["name"] for t in agent.tools}

    return agent


def _do_record_usage(
    user_id: str,
    session_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    surface: str,
    turn_id: Optional[str] = None,
    cached_tokens: int = 0,
) -> None:
    """Persist one turn's token usage. Swallows and logs any failure.

    Kept synchronous and self-contained so it can be unit-tested directly and
    run off the request path from :func:`_record_turn_usage`.
    """
    try:
        cost_monitor.record_usage(
            user_id=user_id,
            session_id=session_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            surface=surface,
            turn_id=turn_id,
            cached_tokens=cached_tokens,
        )
    except Exception:
        logger.exception("token usage recording failed")


def _record_turn_usage(
    agent,
    user_id: str,
    session_id: str,
    model: str,
    surface: str = "text",
    turn_id: Optional[str] = None,
):
    """Fire-and-forget: record real token usage for a completed agent turn.

    Reads the per-turn token counters the agent accumulated across its
    iterations (a fresh agent is created per request, so these hold this turn's
    totals). Recording runs on a daemon thread so a slow/failed Supabase write
    can never slow or break the coach reply. Returns the thread (or ``None`` when
    there is nothing to record) so tests can join it; callers ignore it.
    """
    try:
        prompt_tokens = int(getattr(agent, "session_prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(agent, "session_completion_tokens", 0) or 0)
        # Prompt tokens served from the provider cache (Anthropic cache reads);
        # the only evidence that prompt caching actually works.
        cached_tokens = int(getattr(agent, "session_cache_read_tokens", 0) or 0)
    except Exception:
        return None

    if prompt_tokens <= 0 and completion_tokens <= 0:
        return None

    thread = threading.Thread(
        target=_do_record_usage,
        args=(user_id, session_id, model, prompt_tokens, completion_tokens, surface,
              turn_id, cached_tokens),
        daemon=True,
    )
    thread.start()
    return thread


def _reasoning_config(model: str) -> Optional[dict]:
    """The reasoning setting sent with *model*, or None to leave the framework's own.

    The framework only forwards it for reasoning-capable families and drops it
    elsewhere. Claude answers without extended thinking: with nothing sent the
    framework switches thinking ON at medium effort, and the whole point of a
    Claude tier is an answer in ~2 s (bench 2026-09-27: Haiku 4.5 without
    thinking started answering at 3.6 s p50, DeepSeek with low reasoning 12.5 s).
    """
    effort = config.COACH_REASONING_EFFORT
    if (model or "").startswith("anthropic/") or (effort and effort.lower() in ("none", "off")):
        return {"enabled": False}
    return {"effort": effort} if effort else None


def _gemini_reasoning(model: str) -> Optional[dict]:
    """The thinking level for a Gemini 3 model, or None for any other model.

    Gemini 3 rejects ``enabled: false``, so "none"/"off" becomes "minimal".
    """
    from src.llm_transport import reasoning_for

    return reasoning_for(model)


def _arm_gemini_reasoning(agent) -> None:
    """Send Gemini 3 its thinking level on every call of *agent*.

    The framework forwards reasoning only to "google/gemini-2*" models, so a
    Gemini 3 turn — the deep tier, or any tier after a failover — thought at
    the provider's default. The model is read per call: a failover switches
    ``agent.model`` mid-turn.
    """
    build = getattr(agent, "_build_api_kwargs", None)
    if build is None:
        return

    def _build_api_kwargs(api_messages):
        kwargs = build(api_messages)
        reasoning = _gemini_reasoning(getattr(agent, "model", ""))
        if reasoning and isinstance(kwargs, dict) and "messages" in kwargs:
            kwargs["extra_body"] = {**(kwargs.get("extra_body") or {}), "reasoning": reasoning}
        return kwargs

    agent._build_api_kwargs = _build_api_kwargs


def _turn_fallback_model(routed_model: str) -> Optional[str]:
    """Fallback for this turn, or ``None`` when failover is switched off."""
    if not config.COACH_MODEL_FALLBACK_ENABLED:
        return None
    return fallback_model_for(routed_model)


def _hedge_state(agent) -> dict:
    """The race record of the turn (src/llm_transport.py), {} when there is none."""
    hedge = getattr(agent, "_coach_hedge", None)
    return dict(hedge) if isinstance(hedge, dict) else {}


def _reply_model(reply) -> Optional[str]:
    """The model that wrote a reaction (the backup when it won the race)."""
    model = getattr(reply, "model", None)
    return model if isinstance(model, str) and model else None


def _served_model(agent, routed_model: str) -> str:
    """The model that actually produced the turn (differs after a failover, or
    when the backup won the race against a stalled provider)."""
    hedge = _hedge_state(agent)
    if hedge.get("winner") == "backup" and isinstance(hedge.get("model"), str):
        return hedge["model"]
    served = getattr(agent, "model", None)
    if isinstance(served, str) and served:
        return served
    return routed_model


# Engine lines for text turns run here, not on the default executor that also
# carries the agent and the reaction; engine_note itself caps parallel engines.
_engine_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="engine-note")


def _await_engine_note(future, started: float, state: dict) -> Optional[dict]:
    """The turn's engine line, waiting at most COACH_ENGINE_NOTE_WAIT_MS from *started*.

    Runs on the agent's executor thread. A late or failed analysis never blocks
    the turn: the agent starts without it and can still call the engine itself.
    """
    if future is None:
        return None
    budget = config.COACH_ENGINE_NOTE_WAIT_MS / 1000.0 - (time.monotonic() - started)
    try:
        note = future.result(timeout=max(0.0, budget))
    except FutureTimeout:
        state["timed_out"] = True
        return None
    except Exception:  # noqa: BLE001 — the engine line is best-effort
        logger.debug("engine note failed", exc_info=True)
        return None
    state["ms"] = int((time.monotonic() - started) * 1000)
    state["used"] = bool(note)
    return note


# One line per text turn with its stage timings, for `pm2 logs hermes-chess`.
# The app's own loggers print nothing below WARNING under uvicorn.run (only
# uvicorn's loggers are configured), so this one carries its own handler.
_timings_log = logging.getLogger("hermes.turn_timings")
if not _timings_log.handlers:
    _timings_handler = logging.StreamHandler()
    _timings_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _timings_log.addHandler(_timings_handler)
    _timings_log.setLevel(logging.INFO)
    _timings_log.propagate = False


def _await_review(future, started: float, state: dict) -> Optional[dict]:
    """The game's critical moments, waiting at most COACH_REVIEW_WAIT_MS from *started*.

    A late or failed scan leaves the review to the model's own tools.
    """
    if future is None:
        return None
    budget = config.COACH_REVIEW_WAIT_MS / 1000.0 - (time.monotonic() - started)
    try:
        result = future.result(timeout=max(0.0, budget))
    except FutureTimeout:
        return None
    except Exception:  # noqa: BLE001 — the pre-step is best-effort
        logger.debug("review pre-step failed", exc_info=True)
        return None
    if not isinstance(result, dict) or "error" in result:
        return None
    state["used"] = True
    state["ms"] = int((time.monotonic() - started) * 1000)
    state["moments"] = len(result.get("critical_moments") or [])
    return result


# When the framework exhausts its retries (and any fallback) it RETURNS the
# failure as the final response text instead of raising — on the bench
# (2026-09-23) 19 Gemini turns reached the student as "API call failed after 3
# retries: HTTP 429 …". These prefixes are that text; the turn is treated as an
# error, never as an answer.
_PROVIDER_ERROR_PREFIXES = (
    "API call failed after",
    "Invalid API response after",
    "Context length exceeded",
    "Request payload too large",
)


def _looks_like_provider_error(text: Optional[str]) -> bool:
    return bool(text) and text.lstrip().startswith(_PROVIDER_ERROR_PREFIXES)


_STUDENT_ERROR_TEXT = {
    "ru": "Тренер сейчас недоступен — попробуйте ещё раз через минуту.",
    "kz": "Жаттықтырушы қазір қолжетімсіз — бір минуттан кейін қайталап көріңіз.",
    "kk": "Жаттықтырушы қазір қолжетімсіз — бір минуттан кейін қайталап көріңіз.",
    "en": "The coach is unavailable right now — please try again in a minute.",
}


def _session_language(session, locale: Optional[str]) -> tuple[str, str]:
    """The language the coach answers this session in, and why (see
    prompt_builder.conversation_language): the one the student asked for in any
    message of the session, else the one they write in, else the interface
    locale. One choice for the chat answer, the reaction and the game's move
    comments — the tester (2026-10-01) asked the coach to speak Russian and
    the comments stayed in the interface language."""
    texts = [m.content for m in reversed(session.messages) if m.role == "user"]
    return conversation_language(texts, locale)


def _student_error_text(locale: Optional[str]) -> str:
    """What the student sees when the turn fails: never the provider's text."""
    return _STUDENT_ERROR_TEXT.get((locale or "ru").lower(), _STUDENT_ERROR_TEXT["ru"])


# Notices the framework writes into the reply stream when a provider connection
# dies (English, meant for its own chat UI); they never reach the student.
_FRAMEWORK_STREAM_NOTICES = (
    "⚠ Connection dropped mid tool-call",
    "⚠ Stream stalled mid tool-call",
)


def _is_framework_notice(text: str) -> bool:
    return any(notice in text for notice in _FRAMEWORK_STREAM_NOTICES)


_STREAM_CUT_TEXT = {
    "ru": "(Связь с моделью оборвалась, ответ неполный — задайте вопрос ещё раз.)",
    "kz": "(Модельмен байланыс үзілді, жауап толық емес — сұрағыңызды қайта қойыңыз.)",
    "kk": "(Модельмен байланыс үзілді, жауап толық емес — сұрағыңызды қайта қойыңыз.)",
    "en": "(The connection to the model dropped and the answer is incomplete — please ask again.)",
}


def _watch_stream_cuts(agent) -> None:
    """Flag ``agent._coach_stream_cut`` when a reply stream dies after its first text.

    The framework then ends the turn with what was streamed so far (a retry
    would repeat the text on screen) and says nothing; the chat adds a note
    so the student knows the answer is cut, not finished.
    """
    agent._coach_stream_cut = False
    call = getattr(agent, "_interruptible_streaming_api_call", None)
    if call is None:
        return

    def _streaming_call(*args, **kwargs):
        response = call(*args, **kwargs)
        if getattr(response, "id", None) == "partial-stream-stub":
            agent._coach_stream_cut = True
        return response

    agent._interruptible_streaming_api_call = _streaming_call


def _chunk_text(text: str, size: int = 80):
    """Yield *text* in fixed-size chunks so a buffered reply can be streamed out
    as SSE ``delta`` frames — the same frame type the live-token path emits."""
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _run_bestofn_pipeline(
    *,
    base_agent,
    model: str,
    system_prompt: str,
    session_id: str,
    session_real_id: str,
    user_query: str,
    augmented_message: str,
    user_id: str,
    fen: str,
):
    """Best-of-N (CL Phase 2, Slice 3): generate N buffered candidates, let the
    engine rank the correctness channel, then let the cheap-tier judge pick the
    clearest survivor. Blocking (creates agents + runs a thread pool) — call in
    an executor. Returns ``(BestOfNResult, winner_agent, winner_tool_results)``.

    Candidate 0 reuses the already-created ``base_agent`` (so the turn_start
    telemetry stays accurate and one agent is spared); candidates 1..N-1 are
    fresh agents. Each candidate's real token usage is recorded through the
    existing accounting, and the judge's usage is recorded too.
    """
    import functools

    from src import bestofn

    agents: dict = {}
    tool_results_by_idx: dict = {}

    def _generate(i: int) -> str:
        agent = base_agent if i == 0 else _create_agent(
            model=model, system_prompt=system_prompt, session_id=session_id,
            user_query=user_query,
        )
        # Buffer this candidate's tool outputs so the winner's board actions can
        # be extracted afterwards (candidates are non-streamed — no live frames).
        results: list = []
        agent.tool_complete_callback = (
            lambda _cid, _tn, _args, res: results.append(res)
        )
        text = agent.chat(augmented_message)
        _record_turn_usage(agent, user_id, session_real_id, model, surface="text")
        agents[i] = agent
        tool_results_by_idx[i] = results
        return text

    def _judge_usage(prompt_tokens: int, completion_tokens: int, judge_model: str) -> None:
        _do_record_usage(
            user_id, session_real_id, judge_model,
            prompt_tokens, completion_tokens, "text",
        )

    judge_fn = functools.partial(
        bestofn.run_judge, user_text=user_query,
        model=bestofn.cheap_model(), on_usage=_judge_usage,
    )

    result = bestofn.run_bestofn(
        fen=fen,
        user_text=user_query,
        generate=_generate,
        judge_fn=judge_fn,
        n=config.COACH_BESTOFN_N,
        budget_ms=config.COACH_BESTOFN_BUDGET_MS,
    )
    winner_agent = agents.get(result.selected_idx) or base_agent
    winner_results = tool_results_by_idx.get(result.selected_idx, [])
    return result, winner_agent, winner_results


# ── Health endpoint (enhanced) ─────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint with service status details."""
    import psutil

    process = psutil.Process()
    mem = process.memory_info()

    stockfish_available = shutil.which("stockfish") is not None or os.path.exists(
        os.environ.get("STOCKFISH_PATH") or "/usr/games/stockfish"
    )

    return {
        "status": "ok",
        "service": "hermes-chess-coach",
        "uptime_seconds": round(time.time() - _start_time, 2),
        "memory_mb": round(mem.rss / (1024 * 1024), 2),
        "stockfish": {
            "available": stockfish_available,
            "circuit": stockfish_circuit.status(),
        },
        "supabase": {
            "configured": bool(os.environ.get("SUPABASE_URL")),
            "circuit": supabase_circuit.status(),
        },
    }


@app.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    """OpenAI-compatible chat completions endpoint."""
    _verify_api_key(request)

    # Session management
    session_id = (
        body.session_id
        or request.headers.get("x-hermes-session-id")
        or str(uuid.uuid4())
    )
    user_id = request.headers.get("x-clerk-user-id", "anonymous")

    # Get or create session
    session = await asyncio.to_thread(session_store.get, session_id, user_id)
    if session is None:
        session = await asyncio.to_thread(session_store.create, user_id=user_id, session_id=session_id)

    # Build the user message from the last message in the conversation
    user_message = body.messages[-1].content if body.messages else ""
    if not user_message:
        raise HTTPException(status_code=400, detail="No message content provided")

    # Hygiene: normalize inbound free-text (no-op unless COACH_NORMALIZE_INPUT)
    user_message = _clean_user_text(user_message)

    # Record user message in session
    session.add_message("user", user_message)

    # Load user profile for personalization
    profile = await asyncio.to_thread(_get_voice_profile, user_id)

    # Build personalized system prompt
    system_prompt = await asyncio.to_thread(build_system_prompt, 
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=session.board_state,
    )

    # Route model based on query complexity
    model = _resolve_model(body.model, user_message)

    # Capture the raw current message before history is prepended — tool
    # subsetting scores keyword relevance and prepended history would dilute it.
    raw_user_query = user_message

    # If there's conversation history, prepend it as context
    if len(body.messages) > 1:
        history = "\n".join(
            f"[{m.role}]: {m.content}" for m in body.messages[:-1]
        )
        user_message = f"Previous conversation:\n{history}\n\nCurrent message:\n{user_message}"

    agent = await asyncio.to_thread(_create_agent, 
        model=model, system_prompt=system_prompt, session_id=session_id,
        user_query=raw_user_query, fallback_model=_turn_fallback_model(model),
    )

    # Run the agent in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    try:
        response_text = await loop.run_in_executor(None, agent.chat, user_message)
    except Exception as exc:
        diag.record(
            "agent_error",
            request_id=getattr(request.state, "request_id", None),
            message="agent.chat raised on /v1/chat/completions",
            exc=exc,
            model=model,
        )
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}")

    if not response_text:
        diag.record(
            "empty_response",
            request_id=getattr(request.state, "request_id", None),
            level="warning",
            message="agent returned empty text; served fallback",
            model=model,
            path="/v1/chat/completions",
        )
        response_text = "I wasn't able to generate a response. Please try again."

    # Record real token usage for this turn (fire-and-forget; never blocks/raises)
    _record_turn_usage(agent, user_id, session_id, model, surface="text")

    # Record assistant response in session
    session.add_message("assistant", response_text)

    # Wrap response with board actions envelope
    envelope = wrap_response(response_text)

    response = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=model,
        choices=[
            ChatCompletionChoice(
                message=Message(role="assistant", content=envelope["message"])
            )
        ],
        board_actions=envelope.get("board_actions", []),
    )
    return response


# ── /api/coach/* routes ────────────────────────────────────────────────


class CoachChatRequest(BaseModel):
    message: str
    fen: Optional[str] = None
    session_id: Optional[str] = None
    locale: Optional[str] = None
    # Per-turn grounding the UI adds (e.g. the Review drawer's "[Review context]
    # … classified as blunder …" note). Sent apart from ``message`` so model
    # routing, tool selection, history and memory see the student's actual
    # question; the note only reaches the model for this turn.
    context_note: Optional[str] = None
    # The board (tab) the student is looking at; becomes the session's active
    # board and the target of the coach's board actions this turn.
    board_id: Optional[str] = None


class CoachSessionCreateRequest(BaseModel):
    title: Optional[str] = None


class CoachSessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    active_board_id: Optional[str] = None


class CoachBoardCreateRequest(BaseModel):
    kind: str = "study"
    title: Optional[str] = None
    pgn: Optional[str] = None
    fen: Optional[str] = None
    ply: Optional[int] = None
    orientation: str = "white"
    source: Optional[dict] = None
    activate: bool = True


class CoachBoardUpdateRequest(BaseModel):
    title: Optional[str] = None
    pgn: Optional[str] = None
    # fen: a new study position (drops the loaded game). position: the FEN the
    # student is looking at — a navigation when it belongs to the loaded game.
    fen: Optional[str] = None
    position: Optional[str] = None
    ply: Optional[int] = None
    orientation: Optional[str] = None
    annotations: Optional[dict] = None
    game_state: Optional[dict] = None
    active: Optional[bool] = None


class CoachMessageRequest(BaseModel):
    role: str
    content: str
    source: Optional[str] = None
    # Phase 2 (Task 4): true utterance timestamp (ISO8601, stamped in the browser
    # at turn completion) and the turn correlation id, so voice message rows carry
    # the spoken time — not the write time — and join to coach_events by turn_id.
    client_ts: Optional[str] = None
    turn_id: Optional[str] = None


class CoachImportUrlRequest(BaseModel):
    url: str


class CoachGameStartRequest(BaseModel):
    color: str = "white"          # white | black | random
    elo: int = 1500
    comment_mode: str = "mistakes"  # quiet | mistakes | every


class CoachGameMoveRequest(BaseModel):
    move: str                     # SAN or UCI


class CoachGameCommentRequest(BaseModel):
    locale: Optional[str] = None
    event: str = "move"           # move | end


class CoachFeedbackRequest(BaseModel):
    # turn_id / rating are validated in the handler (returning 400, not 422) so a
    # malformed body is a clean client error per the feedback contract.
    turn_id: Optional[str] = None
    rating: Optional[int] = None
    session_id: Optional[str] = None
    comment: Optional[str] = None
    surface: Optional[str] = None
    client_ts: Optional[str] = None


class CheckoutRequest(BaseModel):
    tier: str
    redirect_url: Optional[str] = None


def _get_user_id(request: Request) -> str:
    """Extract user ID from X-User-Id header (required)."""
    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return user_id


def _sse(data: dict) -> str:
    """Serialize a dict as a single SSE `data:` frame."""
    return f"data: {json.dumps(data)}\n\n"


def _safe_int(value) -> Optional[int]:
    """Coerce *value* to int, returning None for bools / non-numeric / mocks."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _selected_tool_names(agent) -> list[str]:
    """Best-effort list of the tool names available to *agent* (subset-aware)."""
    try:
        return [t["function"]["name"] for t in getattr(agent, "tools", []) or []]
    except Exception:
        return []


def _tool_call_payload(tool_name: str, args, result) -> tuple[bool, Optional[str], dict]:
    """Build (ok, error_code, payload) for a text-path ``tool_call`` event.

    Parses the tool result to classify success/failure, truncates args + a result
    summary for the log, and — for ``check_moves`` — folds in the legal/illegal
    verdict counts (our hallucination metric).
    """
    ok = True
    error_code: Optional[str] = None
    parsed = None
    try:
        parsed = json.loads(result) if isinstance(result, str) else result
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and "error" in parsed:
        ok = False
        error_code = str(parsed.get("error"))[:100]

    payload: dict = {
        "args": str(args)[:500],
        "result_summary": str(result)[:500],
    }

    if tool_name == "check_moves" and isinstance(parsed, dict):
        results = parsed.get("results")
        if isinstance(results, list):
            legal = sum(1 for r in results if isinstance(r, dict) and r.get("legal") is True)
            illegal = len(results) - legal
            payload["check_moves_verdict"] = {
                "candidates": len(results),
                "legal": legal,
                "illegal": illegal,
            }
    return ok, error_code, payload


async def _bestofn_event_stream(
    *,
    base_agent,
    model: str,
    system_prompt: str,
    session_id: str,
    session,
    body,
    augmented_message: str,
    user_id: str,
    turn_id: str,
    prompt_version,
    evt_ctx: dict,
    request: Request,
    loop,
):
    """SSE generator for a best-of-N coach turn (CL Phase 2, Slice 3).

    Runs the buffered generate→engine-rank→judge pipeline off the event loop,
    then emits the winning candidate through the SAME frames as the live path:
    chunked ``delta`` frames, then ``board_actions`` / ``game_results`` (from the
    winner's tool outputs), then the terminal ``done``. Fully fail-open — a
    pipeline exception yields a single ``error`` frame exactly like the normal
    path's LLM failure. The audit row and memory writer run fire-and-forget and
    never block the reply.
    """
    fen = session.board_state
    turn_started = time.monotonic()
    try:
        result, winner_agent, tool_results = await loop.run_in_executor(
            None,
            lambda: _run_bestofn_pipeline(
                base_agent=base_agent, model=model, system_prompt=system_prompt,
                session_id=session_id, session_real_id=session.id,
                user_query=body.message, augmented_message=augmented_message,
                user_id=user_id, fen=fen,
            ),
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error frame
        latency_ms = int((time.monotonic() - turn_started) * 1000)
        log_event(
            "llm_error",
            severity="error",
            surface="text",
            user_id=user_id,
            session_id=session.id,
            turn_id=turn_id,
            model=model,
            duration_ms=latency_ms,
            ok=False,
            error_code=type(exc).__name__,
            payload={"error_class": type(exc).__name__, "message": str(exc)[:2000],
                     "path": "bestofn"},
        )
        diag.record(
            "agent_error",
            request_id=getattr(request.state, "request_id", None),
            message="best-of-N pipeline raised on /api/coach/chat (streaming)",
            exc=exc,
            model=model,
        )
        yield _sse({"error": _student_error_text(body.locale)})
        return

    latency_ms = int((time.monotonic() - turn_started) * 1000)
    response_text = result.text or "I wasn't able to generate a response. Please try again."
    # The winner is buffered text: the live path's filters never saw it. Inline
    # [[arrows: …]] marks reached the student as text (production, 2026-09-28)
    # and so could the framework's stream notices.
    for notice in _FRAMEWORK_STREAM_NOTICES:
        response_text = re.sub(re.escape(notice) + r"[^\n]*", "", response_text)
    response_text, mark_actions = strip_markup(response_text)
    response_text = response_text.strip() or response_text
    if mark_actions:
        board = session.ensure_board()
        for action in mark_actions:
            action.setdefault("board_id", board.id)
        try:
            session.apply_board_actions(mark_actions, board_id=board.id)
        except Exception:
            logger.debug("applying board actions to the session board failed", exc_info=True)
        yield _sse({"board_actions": mark_actions})

    # Stream the buffered winner as chunked deltas (client contract unchanged).
    for chunk in _chunk_text(response_text):
        yield _sse({"delta": chunk})

    # Candidate + judge token usage was recorded inside the pipeline; stamp the
    # assistant row telemetry from the winning candidate's agent.
    prompt_tokens = _safe_int(getattr(winner_agent, "session_prompt_tokens", 0)) or 0
    completion_tokens = _safe_int(getattr(winner_agent, "session_completion_tokens", 0)) or 0

    assistant_extra = {
        "turn_id": turn_id,
        "model": model,
        "prompt_version": prompt_version,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
    }
    session.add_message("assistant", response_text, extra=assistant_extra, evt=evt_ctx)

    log_event(
        "turn_end",
        surface="text",
        user_id=user_id,
        session_id=session.id,
        turn_id=turn_id,
        model=model,
        duration_ms=latency_ms,
        ok=True,
        payload={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
            "finish_reason": "bestofn",
            "bestofn": {
                "n": result.n,
                "selected_idx": result.selected_idx,
                "fallback_reason": result.fallback_reason,
            },
        },
    )

    # Append the audit row fire-and-forget (failure to audit never blocks reply).
    try:
        from src import bestofn

        bestofn.write_audit(result, user_id, session.id, fen)
    except Exception:
        logger.debug("bestofn audit scheduling failed", exc_info=True)

    # Per-student memory (CL Phase 1): same off-request-path treatment as the
    # normal turn path — flag-gated (default OFF) and fully fail-open.
    if config.COACH_MEMORY_WRITER:
        try:
            from src.memory_writer import schedule_memory_writer

            schedule_memory_writer(
                user_id=user_id,
                turn_id=turn_id,
                user_message=body.message,
                coach_reply=response_text,
                board_fen=session.board_state,
                tool_results=list(tool_results),
                model=model,
            )
        except Exception:
            logger.debug("memory writer scheduling failed", exc_info=True)

    envelope = wrap_response(response_text, tool_results=tool_results)

    board_actions = envelope.get("board_actions", [])
    if board_actions:
        yield _sse({"board_actions": board_actions})

    game_results = envelope.get("game_results", [])
    if game_results:
        yield _sse({"game_results": game_results})

    yield _sse({"done": True, "session_id": session.id, "turn_id": turn_id})


async def _small_talk_stream(body, session, user_id: str, turn_id: str, prompt_version: str):
    """A greeting, thanks or goodbye: one fast tool-free reply (the quick model)
    instead of the agent turn. The agent took 3–7 s to say hello, and with the
    two-stage reaction on top it greeted twice (live site, 2026-09-26).
    Streams like a chat answer: ``delta`` frames, then ``done``."""
    from src.quick_reply import build_small_talk_messages, stream_completion

    loop = asyncio.get_event_loop()
    model = quick_model()
    history = [(m.role, m.content) for m in session.messages[:-1]]
    talk_language = _session_language(session, body.locale)[0]
    messages = build_small_talk_messages(body.message, talk_language, history)
    log_event("turn_start", surface="text", user_id=user_id, session_id=session.id, turn_id=turn_id,
              model=model, payload={"small_talk": True, "prompt_version": prompt_version,
                                    "message_length": len(body.message)})
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def _on_delta(text):
        if text:
            loop.call_soon_threadsafe(queue.put_nowait, text)

    def _run():
        try:
            return stream_completion(
                model=model, api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                messages=messages, on_delta=_on_delta, timeout_s=8.0, max_tokens=120, temperature=0.6,
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    started = time.monotonic()
    future = loop.run_in_executor(None, _run)
    parts: list[str] = []
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        parts.append(item)
        yield _sse({"delta": item})
    reply = await future
    text = "".join(parts).strip()
    latency_ms = int((time.monotonic() - started) * 1000)
    if not text:
        log_event("llm_error", severity="warn", surface="text", user_id=user_id, session_id=session.id,
                  turn_id=turn_id, model=model, ok=False,
                  error_code=str(getattr(reply, "error", "") or "empty")[:80], payload={"path": "small_talk"})
        yield _sse({"error": _student_error_text(talk_language)})
        return
    prompt_tokens = getattr(reply, "prompt_tokens", 0) or 0
    completion_tokens = getattr(reply, "completion_tokens", 0) or 0
    if prompt_tokens or completion_tokens:
        threading.Thread(
            target=_do_record_usage,
            args=(user_id, session.id, model, prompt_tokens, completion_tokens, "text", turn_id, 0),
            daemon=True,
        ).start()
    session.add_message(
        "assistant", text,
        extra={"turn_id": turn_id, "model": model, "prompt_version": prompt_version, "latency_ms": latency_ms,
               "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        evt={"user_id": user_id, "turn_id": turn_id, "surface": "text", "model": model},
    )
    log_event("turn_end", surface="text", user_id=user_id, session_id=session.id, turn_id=turn_id,
              model=model, duration_ms=latency_ms, ok=True,
              payload={"small_talk": True, "prompt_tokens": prompt_tokens,
                       "completion_tokens": completion_tokens, "finish_reason": "stop"})
    yield _sse({"done": True, "session_id": session.id, "turn_id": turn_id,
                "active_board_id": session.active_board_id})


@app.post("/api/coach/chat")
async def coach_chat(body: CoachChatRequest, request: Request):
    """Coach chat endpoint — streams the agent's reply as SSE token events.

    Emits, in order: one `{"delta": ...}` frame per streamed text chunk, then
    (if present) `{"board_actions": [...]}` and `{"game_results": [...]}`, and
    finally `{"done": true, "session_id": ...}`. On failure a single
    `{"error": ...}` frame is emitted instead of the trailing events.
    """
    # Stage timings of the turn (ms from the request): logged with turn_end and
    # as one "turn timings" log line, so production shows where time goes.
    request_started = time.monotonic()
    stages: dict = {}

    def _mark(stage: str) -> None:
        stages[stage] = int((time.monotonic() - request_started) * 1000)

    user_id = _get_user_id(request)

    # Rate limiting
    await enforce_rate_limit(request)

    # Analytics
    analytics_tracker.track_chat(user_id, body.session_id or "")

    # The profile depends on the user alone: its (rare) Supabase read starts
    # now and overlaps the session and opening steps below.
    profile_task = asyncio.create_task(asyncio.to_thread(_get_voice_profile, user_id))

    # A new chat sends no session id: the session is created here, without a
    # database lookup for an id that cannot exist yet (one roundtrip saved on
    # the first message of every chat). An id that belongs to someone else, or
    # to nobody, gets a fresh one too — as the voice path does — instead of an
    # upsert over the other user's row.
    session = None
    if body.session_id:
        session = await asyncio.to_thread(session_store.get, body.session_id, user_id)
    if session is None:
        session = await asyncio.to_thread(session_store.create, user_id=user_id)
    session_id = session.id
    _mark("session")

    # Hygiene: normalize inbound free-text (no-op unless COACH_NORMALIZE_INPUT).
    # body.fen is handled separately below and is never normalized.
    body.message = _clean_user_text(body.message)

    # ── Phase-1 turn instrumentation identifiers ──────────────────────────
    # One turn_id correlates the user/assistant coach_messages rows, the
    # token_usage row, and every coach_events row for this turn. prompt_version
    # + the routing decision are captured up front so they can stamp the user
    # message row and the turn_start event. All fail-open (log_event never raises).
    turn_id = new_turn_id()
    prompt_version = get_prompt_version()
    tiers = _model_config.get("tiers", {})
    route = explain_route(body.message, tiers, _model_config["default"])
    model = route["model"]

    msg_extra = {"turn_id": turn_id, "model": model, "prompt_version": prompt_version}
    evt_ctx = {"user_id": user_id, "turn_id": turn_id, "surface": "text", "model": model}
    session.add_message("user", body.message, extra=msg_extra, evt=evt_ctx)

    if body.board_id and session.get_board(body.board_id):
        session.set_active_board(body.board_id)
    if body.fen:
        try:
            session.set_board_state(body.fen, board_id=body.board_id)
        except ValueError:
            pass  # ignore invalid FEN, use existing board state
    active_board = session.ensure_board()

    # Small talk ("Привет", "спасибо") gets one fast tool-free reply instead of
    # the agent loop — see _small_talk_stream.
    from src.quick_reply import is_small_talk

    live_game = active_board.kind == "game" and bool(active_board.game_state)
    # The language of everything said this turn — the reaction, the answer, the
    # rewrite after a wrong sentence: what the student asked for in this session,
    # else the language of their message, else the interface locale.
    turn_language, turn_language_why = _session_language(session, body.locale)
    lang_note = language_note(turn_language, turn_language_why)
    if config.COACH_TWO_STAGE and not body.context_note and not live_game and is_small_talk(body.message):
        return StreamingResponse(
            _small_talk_stream(body, session, user_id, turn_id, prompt_version),
            media_type="text/event-stream",
        )

    # The engine line (see config.COACH_ENGINE_NOTE): Stockfish starts now and runs
    # while the profile loads, the prompt is built and the reaction streams. Not
    # during a live game — the coach must hint there, not hold the best move.
    engine_started = time.monotonic()
    engine_future = None
    # A game in the message: the server loads it and finds its critical moments
    # right away, beside the reaction — the model's first review step did only
    # that (2-3.5 s). COACH_REVIEW_PRESTEP=0 leaves it to the model.
    review_pgn = None
    review_future = None
    if config.COACH_REVIEW_PRESTEP and route.get("reason") == "pgn_in_message" and not live_game:
        from src.model_router import extract_game_pgn
        from src.tools.critical_moments import find_critical_moments

        review_pgn = extract_game_pgn(body.message)
        if review_pgn:
            review_future = _engine_pool.submit(find_critical_moments, review_pgn)
    review_state = {"used": False, "ms": None, "moments": None}
    # An opening named in the message: its book line goes on the board and into
    # the turn before the model is called (src/opening_knowledge.py) — the engine
    # line below then describes the line's final position, not the old board.
    opening_plan = None
    if config.COACH_OPENING_PRESTEP and not live_game and review_future is None:
        try:
            from src.opening_knowledge import plan_opening

            opening_plan = await asyncio.to_thread(
                plan_opening, body.message, session.board_state, active_board.pgn
            )
            if opening_plan and opening_plan.load:
                session.apply_board_actions(
                    [{"type": "load_pgn", "pgn": opening_plan.pgn}], board_id=active_board.id
                )
        except Exception:  # noqa: BLE001 — the pre-step is best-effort
            logger.debug("opening pre-step failed", exc_info=True)
            opening_plan = None
    _mark("opening")
    if (config.COACH_ENGINE_NOTE and (body.fen or opening_plan) and session.board_state
            and not live_game and review_future is None):
        engine_future = _engine_pool.submit(
            engine_note, session.board_state, movetime_ms=config.COACH_ENGINE_NOTE_MOVETIME_MS
        )
    engine_state = {"used": False, "ms": None, "timed_out": False}
    # The student's idea on the board (src/hypothetical.py): the moves the
    # message names («а если Rg1?», «поставить ладью на g1») are played and
    # looked at by the engine now, beside the engine line — in a live game too,
    # since the student asks about their own move there.
    named_moves: list = []
    hypo_future = None
    hypo_state = {"used": False, "ms": None, "timed_out": False, "moves": 0}
    if session.board_state:
        try:
            from src.prompt_builder import question_moves

            named_moves = question_moves(body.message, session.board_state)
            legal_named = [q for q in named_moves if q.get("legal")]
            hypo_state["moves"] = len(legal_named)
            if legal_named and config.COACH_HYPOTHETICAL_NOTE:
                from src.hypothetical import hypothetical_notes

                hypo_future = _engine_pool.submit(
                    hypothetical_notes, session.board_state, legal_named,
                    config.COACH_HYPOTHETICAL_MOVETIME_MS, not live_game,
                )
        except Exception:  # noqa: BLE001 — the idea block is best-effort
            logger.debug("question moves failed", exc_info=True)
            named_moves = []

    # The agent does not depend on the prompt (it only stores it), so it is
    # built while the profile arrives and the prompt is assembled.
    fallback_model = _turn_fallback_model(model)
    agent_task = asyncio.create_task(asyncio.to_thread(
        _create_agent, model=model, system_prompt="", session_id=session_id,
        user_query=body.message, fallback_model=fallback_model,
    ))
    profile = await profile_task
    _mark("profile")
    # Static persona/tool guidance stays in the system prompt (cacheable);
    # date, profile, memory and board state travel in the user message.
    system_prompt, turn_context = await asyncio.to_thread(build_system_prompt, 
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=session.board_state,
        locale=body.locale,
        return_parts=True,
    )
    _mark("prompt")
    logger.info("Model routed: %s for message: %s", model, body.message[:80])

    # Build conversation context from session history (exclude the just-added user message)
    history_messages = session.messages[:-1]
    current_message = (
        f"{body.context_note.strip()}\n\n{body.message}" if body.context_note else body.message
    )
    # A live game on the active board: the coach must know it is playing, what
    # has been played, and that hints are hints (see game_mode.game_context).
    if active_board.kind == "game" and active_board.game_state:
        try:
            from src.game_mode import game_context

            game_note = game_context(active_board)
            if game_note:
                turn_context = f"{turn_context}\n\n{game_note}" if turn_context else game_note
        except Exception:  # noqa: BLE001 — never block a turn on the game note
            logger.debug("game context failed", exc_info=True)
    # Moves the student named («могу ли я сыграть Qxg7?»): their legality is a
    # fact of the board, decided here, not left to the model.
    try:
        from src.prompt_builder import moves_in_question_block

        moves_note = moves_in_question_block(body.message, session.board_state, named_moves or None)
        if moves_note:
            turn_context = f"{turn_context}\n\n{moves_note}" if turn_context else moves_note
    except Exception:  # noqa: BLE001 — never block a turn on this
        logger.debug("moves-in-question block failed", exc_info=True)
    current_message = attach_turn_context(current_message, turn_context)
    if history_messages:
        recent = history_messages[-20:]  # last ~10 turns
        history_text = "\n".join(f"[{m.role}]: {m.content}" for m in recent)
        augmented_message = f"Previous conversation:\n{history_text}\n\nCurrent message:\n{current_message}"
    else:
        augmented_message = current_message

    agent = await agent_task
    agent.ephemeral_system_prompt = system_prompt
    _mark("agent")

    log_event(
        "turn_start",
        surface="text",
        user_id=user_id,
        session_id=session.id,
        turn_id=turn_id,
        model=model,
        payload={
            "routing_tier": route["tier"],
            "routing_reason": route["reason"],
            "routing_matched": route["matched"],
            "message_length": len(body.message),
            "fen": session.board_state if body.fen else None,
            "prompt_version": prompt_version,
            "tools_selected": _selected_tool_names(agent),
            "fallback_model": fallback_model,
            "two_stage": bool(config.COACH_TWO_STAGE),
            "opening": opening_plan.name if opening_plan else None,
            "opening_loaded": bool(opening_plan and opening_plan.load),
        },
    )

    # Capture tool results for board action extraction
    tool_results: list[str] = []

    loop = asyncio.get_event_loop()

    async def event_stream():
        # Best-of-N (CL Phase 2, Slice 3): flag-gated AND only on a FEN-anchored
        # turn. Candidates are generated buffered (non-streamed); the engine
        # ranks the correctness channel and the cheap-tier judge picks the
        # clearest survivor; the winner is then emitted through this same SSE
        # machinery (chunked deltas + the same terminal frames) so the client
        # contract is unchanged. Flag OFF or no FEN → the original single-streamed
        # path below runs, byte-identical. The FEN-anchored signal is an
        # explicit body.fen on this turn (the position the student is asking
        # about) — a chit-chat turn carries no fen and always takes the normal
        # path, even though the session always holds a default board position.
        if config.COACH_BESTOFN and body.fen and session.board_state:
            # Fail-open on pipeline import/setup errors (before any candidate is
            # generated): if the best-of-N module can't be imported/prepared,
            # degrade to the NORMAL streaming path instead of emitting an SSE
            # error frame. Prod incident 2026-09-09: src.eval/src.optimize were
            # missing, so this import raised and the error escaped to the client.
            bestofn_ready = True
            try:
                from src import bestofn  # noqa: F401 — pre-flight import check
            except Exception:
                logger.warning(
                    "best-of-N unavailable (pipeline import/setup failed); "
                    "falling back to normal streaming path", exc_info=True,
                )
                bestofn_ready = False

            if bestofn_ready:
                # The candidates get the turn's engine line too — without it each
                # one called analyze_position itself (or answered without it).
                note = await loop.run_in_executor(
                    None, _await_engine_note, engine_future, engine_started, engine_state
                )
                bestofn_message = augmented_message
                if opening_plan:
                    bestofn_message = f"{bestofn_message}\n\n{opening_plan.block}"
                if note:
                    bestofn_message = (f"{bestofn_message}\n\n"
                                       f"{engine_note_block(note['note'], opening=bool(opening_plan and not opening_plan.relative))}")
                bestofn_message = f"{bestofn_message}\n\n{lang_note}"
                async for frame in _bestofn_event_stream(
                    base_agent=agent, model=model, system_prompt=system_prompt,
                    session_id=session_id, session=session, body=body,
                    augmented_message=bestofn_message, user_id=user_id,
                    turn_id=turn_id, prompt_version=prompt_version, evt_ctx=evt_ctx,
                    request=request, loop=loop,
                ):
                    yield frame
                return

        # Bridge the agent's synchronous, executor-thread token callback onto the
        # event loop via a thread-safe queue so tokens stream out as they arrive.
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        streamed_any = False  # the ANSWER stage produced at least one delta
        # Per-turn state used by the coach_events instrumentation below.
        tool_starts: dict = {}
        partial_parts: list[str] = []
        answer_parts: list[str] = []  # the answer stage's deltas, as streamed
        markup = MarkupFilter()
        streamed_chars = 0

        # The answer check (src/answer_check.py): the positions a written move may
        # belong to (the board, the opening line, the game, what tools put on the
        # board), a gate that holds each sentence until it is checked, and one
        # rewrite of the rest of the answer after a wrong sentence.
        from src.answer_check import CheckContext, SentenceGate, fix_messages, proposed_move, strip_leaks

        # Every board of the session counts (a capture named for the second
        # board was cut as impossible on the first, 2026-10-02), and in a game
        # the student's colour decides whose «твой конь» is.
        student_color = None
        if live_game:
            student_color = chess.WHITE if active_board.game_state.get("student_color") == "white" else chess.BLACK
        check_ctx = CheckContext.from_fens(
            [session.board_state, body.fen] + [b.fen for b in session.boards]
            + [q["after_fen"] for q in named_moves if q.get("after_fen")],  # the positions the student's idea leads to
            [p for p in (active_board.pgn, review_pgn, opening_plan.pgn if opening_plan else None) if p]
            + [b["line"] for b in (opening_plan.branches if opening_plan else [])]
            + [b.pgn for b in session.boards if b.pgn and b.id != active_board.id],
            question=body.message,
            student_color=student_color,
        )
        check_ctx.language = turn_language  # a sentence in the wrong language is rewritten like a wrong move
        gate = SentenceGate(check_ctx, enabled=bool(config.COACH_ANSWER_CHECK))
        fix_gate = SentenceGate(check_ctx, enabled=bool(config.COACH_ANSWER_CHECK))
        fix_markup = MarkupFilter()
        # The coach's recommendation («сыграй Rg1») is checked by the engine
        # before the sentence is shown (src/hypothetical.verify_recommendation).
        verify_state = {"left": config.COACH_MOVE_VERIFY_PER_TURN if config.COACH_MOVE_VERIFY else 0,
                        "checked": 0, "caught": 0, "ms": 0}
        fix = {"running": False, "done": False, "sentence": None, "issues": [], "dropped": [],
               "reply": None, "started": None, "first_ms": None, "emitted": False,
               "shown_prefix": "", "head": ""}
        turn_msg = {"message": None}

        # ── Two-stage answer ──────────────────────────────────────────────
        # A tool-free one-sentence reaction streams first while the agent is
        # still calling the engine; the answer follows after a blank line in
        # the same assistant message (concatenated deltas stay one text, so
        # every existing client renders it unchanged). ``stage`` frames mark
        # the boundary for clients that want to style the two parts.
        #
        # Ordering guarantee: while the reaction is streaming, answer deltas
        # are held back and flushed right after the separator; if the answer
        # starts before the reaction has produced a single token, the
        # reaction is abandoned and the answer streams immediately — the
        # first stage can only ever make the reply feel faster, never later.
        from src.quick_reply import wants_reaction

        two_stage = bool(config.COACH_TWO_STAGE) and wants_reaction(body.message, bool(body.fen))
        quick = {
            "shown": False,      # at least one reaction delta went to the client
            "finished": not two_stage,  # reaction done / abandoned / disabled
            "abort": False,      # polled by the reaction thread between chunks
            "parts": [],
            "reply": None,
        }
        held_answer: list[str] = []
        quick_model_id = quick_model() if two_stage else None
        answer_has_text = False  # a non-blank answer delta has gone out

        def _answer_delta(text: str) -> Optional[str]:
            """Drop the blank lines some models open with — after the reaction
            and the separator they would show as a hole in the message."""
            nonlocal answer_has_text
            if answer_has_text or not quick["shown"]:
                answer_has_text = answer_has_text or bool(text.strip())
                return text
            text = text.lstrip()
            if not text:
                return None
            answer_has_text = True
            return text

        def _on_delta(text):
            if text:
                loop.call_soon_threadsafe(queue.put_nowait, ("delta", text))

        def _on_quick_delta(text):
            if text and not quick["abort"]:
                loop.call_soon_threadsafe(queue.put_nowait, ("quick", text))

        def _run_quick():
            reply = None
            try:
                from src.quick_reply import stream_quick_reply

                reply = stream_quick_reply(
                    model=quick_model_id,
                    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    message=body.message,
                    locale=turn_language,
                    board_fen=session.board_state if body.fen else None,
                    on_delta=_on_quick_delta,
                    timeout_s=max(0.5, config.COACH_QUICK_BUDGET_MS / 1000.0),
                    max_tokens=config.COACH_QUICK_MAX_TOKENS,
                    should_abort=lambda: quick["abort"],
                )
            except Exception:  # noqa: BLE001 — the first stage is best-effort
                logger.debug("quick reaction crashed", exc_info=True)
            finally:
                # Always unblock the stream loop, whatever happened above.
                loop.call_soon_threadsafe(queue.put_nowait, ("quick_done", reply))

        # Tool-activity frames: emit tool_call when a tool starts and tool_result
        # when it completes so the frontend's ToolIndicator lights up during a
        # tool-using exchange. Callbacks run on the executor thread, so hop onto
        # the loop via call_soon_threadsafe (same bridge as _on_delta).
        def _on_tool_start(tool_call_id, tool_name, args):
            tool_starts[tool_call_id] = time.monotonic()
            loop.call_soon_threadsafe(queue.put_nowait, ("tool_call", tool_name))

        def _on_tool_complete(tool_call_id, tool_name, args, result):
            logger.info(
                "Tool called: %s args=%s result=%s",
                tool_name, str(args)[:200], str(result)[:200],
            )
            tool_results.append(result)
            # The board changes go out the moment the tool finishes: the arrows
            # of an answer used to reach the student only when the whole turn was
            # over, seconds after the text that talks about them.
            actions = tool_board_actions(result)
            if actions:
                loop.call_soon_threadsafe(queue.put_nowait, ("board_actions", actions))
            # What the tool put on the board (a topic example, a puzzle, a game)
            # is a position the answer may talk about.
            try:
                check_ctx.add_text(result if isinstance(result, str) else json.dumps(result))
                for action in actions or []:
                    if isinstance(action, dict):
                        check_ctx.add(action.get("fen"))
                        if action.get("pgn"):
                            check_ctx.add_line(action["pgn"])
            except Exception:  # noqa: BLE001 — the check must never break a turn
                logger.debug("answer check context update failed", exc_info=True)
            started = tool_starts.pop(tool_call_id, None)
            duration_ms = int((time.monotonic() - started) * 1000) if started else None
            ok, error_code, payload = _tool_call_payload(tool_name, args, result)
            # Persist the tool call — this is the key gap (text tool calls were
            # ephemeral SSE frames only). Runs on the executor thread; log_event
            # is fail-open and off the async hot path.
            log_event(
                "tool_call",
                severity="info" if ok else "warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=model,
                tool_name=tool_name,
                duration_ms=duration_ms,
                ok=ok,
                error_code=error_code,
                payload=payload,
            )
            loop.call_soon_threadsafe(
                queue.put_nowait, ("tool_result", {"tool": tool_name, "ok": ok})
            )

        agent.tool_start_callback = _on_tool_start
        agent.tool_complete_callback = _on_tool_complete

        def _run():
            try:
                # Waits on this executor thread, so the reaction keeps streaming.
                note = _await_engine_note(engine_future, engine_started, engine_state)
                message = augmented_message
                if opening_plan:
                    message = f"{message}\n\n{opening_plan.block}"
                if note:
                    message = f"{message}\n\n{engine_note_block(note['note'], opening=bool(opening_plan and not opening_plan.relative))}"
                hypo = _await_engine_note(hypo_future, engine_started, hypo_state)
                if hypo:
                    message = f"{message}\n\n{hypothetical_block(hypo['note'], live_game=bool(live_game))}"
                review = _await_review(review_future, engine_started, review_state)
                if review:
                    message = f"{message}\n\n{review_block(review)}"
                message = f"{message}\n\n{lang_note}"
                turn_msg["message"] = message
                result = agent.chat(message, stream_callback=_on_delta)
                loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
            except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error frame
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        def _run_fix(shown: str, wrong: str, issues: list):
            """The rest of the answer after a wrong sentence: one tool-free call."""
            reply = None
            try:
                from src.quick_reply import stream_completion

                reply = stream_completion(
                    model=model,
                    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    messages=fix_messages(turn_msg["message"] or augmented_message, shown, wrong, issues,
                                          lang_note),
                    on_delta=lambda text: loop.call_soon_threadsafe(queue.put_nowait, ("fix", text)),
                    timeout_s=config.COACH_ANSWER_FIX_TIMEOUT_S,
                    max_tokens=config.COACH_ANSWER_FIX_MAX_TOKENS,
                    temperature=0.4,
                )
            except Exception:  # noqa: BLE001 — without the rewrite the wrong part is just left out
                logger.debug("answer fix crashed", exc_info=True)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, ("fix_done", reply))

        turn_started = time.monotonic()
        quick_future = loop.run_in_executor(None, _run_quick) if two_stage else None
        future = loop.run_in_executor(None, _run)

        result_text = None
        error_exc = None
        main_done = False

        def _board_frame(actions: list) -> str:
            """Apply *actions* to the session's board record (so the position survives
            a reload) and frame them, each tagged with the board (tab) it hit.
            Arrows a piece on the board cannot draw are dropped (board_markup.prune_arrows)."""
            actions = [a for a in (prune_arrows(a, session.board_state) for a in actions) if a]
            if not actions:
                return ""
            try:
                for action in actions:
                    if isinstance(action, dict):
                        action.setdefault("board_id", active_board.id)
                session.apply_board_actions(actions, board_id=active_board.id)
            except Exception:
                logger.debug("applying board actions to the session board failed", exc_info=True)
            return _sse({"board_actions": actions})

        def _finish_quick():
            """Close the reaction stage: separator + stage marker if it was shown."""
            frames = []
            if quick["shown"]:
                sep = "\n\n"
                partial_parts.append(sep)
                frames.append(_sse({"delta": sep}))
                frames.append(_sse({"stage": "answer"}))
            for held in held_answer:
                held = _answer_delta(held)
                if held:
                    frames.append(_sse({"delta": held}))
            held_answer.clear()
            quick["finished"] = True
            return frames

        def _answer_frames(text: str) -> list:
            """Frames for answer text that passed the check (the stream as before)."""
            nonlocal streamed_chars
            text = strip_leaks(text)  # DeepSeek's tool-call markup written as text
            # A mark on a line of its own leaves an empty paragraph behind.
            if text.startswith("\n") and answer_parts and answer_parts[-1].endswith("\n\n"):
                text = text.lstrip("\n")
            text = re.sub(r"\n{3,}", "\n\n", text)
            if not text:
                return []
            if "answer_shown" not in stages:
                _mark("answer_shown")
            partial_parts.append(text)
            answer_parts.append(text)
            streamed_chars += len(text)
            frames = []
            if quick["finished"]:
                text = _answer_delta(text)
                if text:
                    frames.append(_sse({"delta": text}))
            elif not quick["shown"]:
                # The answer got here first — abandon the reaction.
                quick["abort"] = True
                frames.extend(_finish_quick())
                frames.append(_sse({"delta": text}))
            else:
                held_answer.append(text)
            return frames

        def _sentence_frames(pairs, source: str) -> list:
            """Checked sentences → frames. A wrong sentence of the model's answer is
            not shown and starts the rewrite (which replaces the rest of the draft);
            a wrong sentence of the rewrite is left out."""
            frames = []
            for text, issues, sentence in pairs:
                if source == "agent" and (fix["running"] or fix["done"]):
                    continue  # the rewrite stands in for the rest of the draft
                if issues:
                    logger.info("answer check: %s | %s", "; ".join(issues), sentence.strip()[:200])
                    if source == "agent" and config.COACH_ANSWER_FIX:
                        # The start of the sentence that already went out (before its
                        # first move or piece): the rewrite must not say it again.
                        fix.update(running=True, sentence=sentence, issues=issues, started=time.monotonic(),
                                   shown_prefix=sentence[: len(sentence) - len(text)] if sentence.endswith(text) else "")
                        loop.run_in_executor(None, _run_fix, "".join(answer_parts), sentence, issues)
                    else:
                        fix["dropped"].append({"sentence": sentence.strip()[:300], "issues": issues})
                    continue
                frames.extend(_answer_frames(text))
            return frames

        async def _verified(pairs):
            """A sentence that recommends a move waits for the engine's word on
            it (a few hundred ms, off the event loop); a move that gives away
            material or the game is treated like a wrong claim — not shown,
            the rest rewritten from the engine's facts."""
            if verify_state["left"] <= 0 or check_ctx.current is None:
                return pairs
            out = []
            for text, issues, sentence in pairs:
                if not issues and verify_state["left"] > 0:
                    found = proposed_move(sentence, check_ctx)
                    if found:
                        from src.hypothetical import verify_recommendation

                        verify_state["left"] -= 1
                        verify_state["checked"] += 1
                        started_v = time.monotonic()
                        try:
                            issue = await loop.run_in_executor(
                                _engine_pool, verify_recommendation, found[0], found[1], found[2],
                                config.COACH_MOVE_VERIFY_MOVETIME_MS, config.COACH_MOVE_VERIFY_CP, not live_game,
                            )
                        except Exception:  # noqa: BLE001 — the check is best-effort
                            logger.debug("move verification failed", exc_info=True)
                            issue = None
                        verify_state["ms"] += int((time.monotonic() - started_v) * 1000)
                        if issue:
                            verify_state["caught"] += 1
                            issues = [issue]
                out.append((text, issues, sentence))
            return out

        if review_pgn and review_future is not None:
            # The game goes on the board at once, before any word of the review.
            yield _board_frame([{"type": "load_pgn", "pgn": review_pgn}])
        if opening_plan and opening_plan.load:
            # So does the opening the student asked about — applied to the
            # session board already (before the engine note); this frame only
            # shows it, without a second replay and a second pair of writes.
            yield _sse({"board_actions": [{"type": "load_pgn", "pgn": opening_plan.pgn,
                                           "board_id": active_board.id}]})

        try:
            while not (main_done and quick["finished"] and not fix["running"]):
                item = await queue.get()
                if item is sentinel:
                    main_done = True
                    # The end of the draft: an unfinished "[[" was not a mark, and
                    # the last sentence gets its check too.
                    tail = markup.flush()
                    for frame in _sentence_frames(await _verified((gate.feed(tail) if tail else []) + gate.flush()), "agent"):
                        yield frame
                    if not quick["finished"] and not quick["shown"]:
                        # Answer complete, reaction never started: drop it.
                        quick["abort"] = True
                        for frame in _finish_quick():
                            yield frame
                    continue
                kind, payload = item
                if kind == "quick":
                    if quick["finished"] or quick["abort"]:
                        continue  # late chunk of an abandoned reaction
                    if not quick["shown"]:
                        quick["shown"] = True
                        _mark("reaction_first")
                        yield _sse({"stage": "quick"})
                    quick["parts"].append(payload)
                    partial_parts.append(payload)
                    streamed_chars += len(payload)
                    yield _sse({"delta": payload})
                elif kind == "quick_done":
                    quick["reply"] = payload
                    if not quick["finished"]:
                        for frame in _finish_quick():
                            yield frame
                elif kind == "delta":
                    if _is_framework_notice(payload):
                        continue
                    if not streamed_any:
                        _mark("answer_first")
                    streamed_any = True
                    if fix["running"] or fix["done"]:
                        continue  # the draft after a wrong sentence is replaced
                    # Inline [[arrows: …]] / [[squares: …]] marks become board
                    # actions now and never reach the text (src/board_markup.py).
                    payload, mark_actions = markup.feed(payload)
                    for action in mark_actions:
                        yield _board_frame([action])
                    if not payload:
                        continue
                    # Each sentence goes out once it is complete and checked.
                    for frame in _sentence_frames(await _verified(gate.feed(payload)), "agent"):
                        yield frame
                elif kind == "fix":
                    if not fix["running"] or not payload:
                        continue
                    if not fix["emitted"]:
                        # Hold the first characters until the shown start of the
                        # sentence can be compared: a model told to continue after
                        # «Take on» sometimes writes «Take on d5 …» again (2026-09-30).
                        prefix = fix["shown_prefix"].strip()
                        fix["head"] += payload
                        if prefix and len(fix["head"].strip()) < len(prefix) + 2:
                            continue
                        payload, fix["head"] = fix["head"], ""
                        if prefix and payload.lstrip().lower().startswith(prefix.lower()):
                            payload = payload.lstrip()[len(prefix):]
                            if not payload:
                                continue
                        elif prefix:
                            # «Самое упорное здесь — отвести» shown, the rewrite opens
                            # «Самое упорное здесь — увести ладью…» (stand, 2026-10-04):
                            # the same start with the last word changed is dropped whole.
                            pw, hw = prefix.split(), payload.lstrip().split()
                            common = 0
                            for a, b in zip(pw, hw):
                                if a.lower().strip(",.;:—–-«»\"") != b.lower().strip(",.;:—–-«»\""):
                                    break
                                common += 1
                            if common >= max(2, (len(pw) * 3 + 4) // 5):
                                payload = " ".join(hw[len(pw):])
                                if not payload:
                                    continue
                        fix["emitted"] = True
                        fix["first_ms"] = int((time.monotonic() - fix["started"]) * 1000)
                        shown = "".join(answer_parts)
                        if shown and shown[-1].isspace():
                            payload = payload.lstrip(" ")
                        elif shown and not payload[0].isspace():
                            payload = " " + payload
                        if not payload:
                            continue
                    payload, mark_actions = fix_markup.feed(payload)
                    for action in mark_actions:
                        yield _board_frame([action])
                    for frame in _sentence_frames(await _verified(fix_gate.feed(payload)), "fix"):
                        yield frame
                elif kind == "fix_done":
                    fix["reply"] = payload
                    if fix["head"] and not fix["emitted"]:
                        # A rewrite shorter than the held prefix: send it as it is.
                        head, fix["head"] = fix["head"], ""
                        fix["emitted"] = True
                        head, mark_actions = fix_markup.feed(head)
                        for action in mark_actions:
                            yield _board_frame([action])
                        for frame in _sentence_frames(await _verified(fix_gate.feed(head)), "fix"):
                            yield frame
                    tail = fix_markup.flush()
                    for frame in _sentence_frames(await _verified((fix_gate.feed(tail) if tail else []) + fix_gate.flush()), "fix"):
                        yield frame
                    fix["running"] = False
                    fix["done"] = True
                elif kind == "tool_call":
                    yield _sse({"tool_call": payload})
                elif kind == "tool_result":
                    yield _sse({"tool_result": payload})
                elif kind == "board_actions":
                    yield _board_frame(payload)
                elif kind == "result":
                    result_text = payload
                elif kind == "error":
                    error_exc = payload
            if streamed_any and getattr(agent, "_coach_stream_cut", False) is True and error_exc is None:
                cut_note = "\n\n" + _STREAM_CUT_TEXT.get(turn_language, _STREAM_CUT_TEXT["ru"])
                partial_parts.append(cut_note)
                answer_parts.append(cut_note)
                yield _sse({"delta": cut_note})
            await future  # ensure the executor thread has fully unwound
            if quick_future is not None and quick["reply"] is not None:
                await quick_future
            # An abandoned reaction is left to time out on its thread: waiting
            # for it here would delay the terminal frames for nothing.
        except (asyncio.CancelledError, GeneratorExit):
            quick["abort"] = True
            # Client disconnected mid-stream: record what we streamed so far and
            # the partial assistant text, then re-raise so Starlette unwinds.
            log_event(
                "stream_disconnect",
                severity="warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=model,
                payload={
                    "chars_streamed": streamed_chars,
                    "partial_text": "".join(partial_parts)[:2000],
                },
            )
            raise

        latency_ms = int((time.monotonic() - turn_started) * 1000)

        # The model that answered: after a failover the agent has switched
        # itself to the fallback, and cost/telemetry must follow it.
        served_model = _served_model(agent, model)
        if served_model != model:
            log_event(
                "model_fallback",
                severity="warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=served_model,
                payload={"routed_model": model, "served_model": served_model},
            )

        # First-stage telemetry (whether or not it reached the screen).
        quick_reply = quick["reply"]
        quick_text = "".join(quick["parts"]).strip() if quick["shown"] else ""
        if two_stage:
            log_event(
                "quick_reaction",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=_reply_model(quick_reply) or quick_model_id,
                duration_ms=getattr(quick_reply, "latency_ms", None),
                ok=bool(quick_text),
                error_code=getattr(quick_reply, "error", None) if quick_reply else "no_reply",
                payload={
                    "shown": bool(quick_text),
                    "first_token_ms": getattr(quick_reply, "first_token_ms", None),
                    "chars": len(quick_text),
                    "abandoned": bool(quick["abort"]),
                },
            )
            if quick_reply is not None and (quick_reply.prompt_tokens or quick_reply.completion_tokens):
                threading.Thread(
                    target=_do_record_usage,
                    args=(user_id, session.id, _reply_model(quick_reply) or quick_model_id, quick_reply.prompt_tokens,
                          quick_reply.completion_tokens, "text", turn_id, 0),
                    daemon=True,
                ).start()

        # The answer check: what was stopped and how the rest was written.
        fix_reply = fix["reply"]
        answer_check = {
            "fixed": bool(fix["sentence"]),
            "issues": fix["issues"],
            "sentence": (fix["sentence"] or "").strip()[:300] or None,
            "fix_first_ms": fix["first_ms"],
            "fix_model": _reply_model(fix_reply) if fix_reply is not None else None,
            "fix_error": getattr(fix_reply, "error", None) if fix_reply is not None else None,
            "dropped": fix["dropped"],
        }
        if answer_check["fixed"] or answer_check["dropped"]:
            log_event(
                "answer_check",
                severity="warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=model,
                payload=answer_check,
            )
        if fix_reply is not None and (fix_reply.prompt_tokens or fix_reply.completion_tokens):
            threading.Thread(
                target=_do_record_usage,
                args=(user_id, session.id, _reply_model(fix_reply) or model, fix_reply.prompt_tokens,
                      fix_reply.completion_tokens, "text", turn_id, 0),
                daemon=True,
            ).start()

        # A provider failure returned AS TEXT is an error, not an answer.
        provider_error_text = result_text if _looks_like_provider_error(result_text) else None
        if provider_error_text and error_exc is None:
            error_exc = RuntimeError(provider_error_text)

        if error_exc is not None:
            # Streaming-path LLM failure — previously left ZERO trace. Emit the
            # event AND write a diagnostic (the streaming path never did before).
            error_code = "provider_error" if provider_error_text else type(error_exc).__name__
            log_event(
                "llm_error",
                severity="error",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=served_model,
                duration_ms=latency_ms,
                ok=False,
                error_code=error_code,
                payload={"error_class": type(error_exc).__name__, "message": str(error_exc)[:2000],
                         "routed_model": model, "fallback_model": fallback_model},
            )
            diag.record(
                "agent_error",
                request_id=getattr(request.state, "request_id", None),
                message="agent.chat raised on /api/coach/chat (streaming)"
                if not provider_error_text else
                "agent.chat returned a provider error as text on /api/coach/chat",
                exc=error_exc,
                model=served_model,
            )
            # The student gets one calm sentence in their language; the
            # provider's text stays in the logs.
            yield _sse({"error": _student_error_text(turn_language)})
            return

        # Iteration cap / empty-response warnings (best-effort attribute reads).
        iterations = _safe_int(getattr(agent, "_api_call_count", None))
        max_iter = _safe_int(getattr(agent, "max_iterations", None))
        hit_max = bool(iterations is not None and max_iter is not None and iterations >= max_iter)
        if hit_max:
            log_event(
                "max_iterations_hit",
                severity="warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=served_model,
                payload={"iterations": iterations, "max_iterations": max_iter},
            )

        if not result_text:
            log_event(
                "empty_response",
                severity="warn",
                surface="text",
                user_id=user_id,
                session_id=session.id,
                turn_id=turn_id,
                model=served_model,
                payload={"path": "/api/coach/chat"},
            )

        answer_text = result_text or "I wasn't able to generate a response. Please try again."
        if quick_text:
            answer_text = answer_text.lstrip()

        # If the agent produced no token stream (no callback support / tool-only
        # turn), fall back to emitting the completed text as a single delta so the
        # concatenated deltas always reconstruct the full assistant message.
        if not streamed_any:
            answer_text, mark_actions = strip_markup(answer_text)
            for action in mark_actions:
                yield _board_frame([action])
            yield _sse({"delta": answer_text})

        # What the student saw, as one message: reaction, blank line, answer. Text
        # the model writes alongside a tool call streams too but is not part of
        # the final message, so the stored answer is the streamed one.
        streamed_answer = re.sub(r"<think>.*?</think>\s*", "", "".join(answer_parts), flags=re.DOTALL).strip()
        if streamed_any and streamed_answer:
            answer_text = streamed_answer
        response_text = f"{quick_text}\n\n{answer_text}" if quick_text else answer_text

        # Record real token usage for this turn (fire-and-forget; never blocks)
        _record_turn_usage(agent, user_id, session.id, served_model, surface="text", turn_id=turn_id)

        prompt_tokens = _safe_int(getattr(agent, "session_prompt_tokens", 0)) or 0
        completion_tokens = _safe_int(getattr(agent, "session_completion_tokens", 0)) or 0

        # Stamp the assistant row with the full turn telemetry (fail-soft on
        # pre-migration prod: persist_message retries without the new columns).
        assistant_extra = {
            "turn_id": turn_id,
            "model": served_model,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        session.add_message("assistant", response_text, extra=assistant_extra, evt=evt_ctx)

        finish_reason = "empty" if not result_text else ("max_iterations" if hit_max else "stop")
        if config.COACH_EMIT_USAGE:
            # Bench/diagnostics only (COACH_EMIT_USAGE=1): expose the turn's
            # telemetry to the client before the terminal frame.
            yield _sse({"usage": {
                "model": served_model, "routed_model": model, "routing_tier": route["tier"],
                "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "cached_tokens": _safe_int(getattr(agent, "session_cache_read_tokens", 0)) or 0,
                "latency_ms": latency_ms, "iterations": iterations, "finish_reason": finish_reason,
                "tools_selected": _selected_tool_names(agent),
                "engine_note": dict(engine_state), "hypothetical": dict(hypo_state), "move_verify": dict(verify_state),
                "review": dict(review_state),
                "stages_ms": dict(stages),
                "hedge": _hedge_state(agent),
                "answer_check": answer_check,
                "opening": opening_plan.name if opening_plan else None,
                "quick": {
                    "model": _reply_model(quick_reply) or quick_model_id, "shown": bool(quick_text),
                    "first_token_ms": getattr(quick_reply, "first_token_ms", None),
                    "latency_ms": getattr(quick_reply, "latency_ms", None),
                    "error": getattr(quick_reply, "error", None) if quick_reply else None,
                } if two_stage else None,
            }})
        log_event(
            "turn_end",
            surface="text",
            user_id=user_id,
            session_id=session.id,
            turn_id=turn_id,
            model=served_model,
            duration_ms=latency_ms,
            ok=True,
            payload={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "latency_ms": latency_ms,
                "iterations": iterations,
                "finish_reason": finish_reason,
                "routed_model": model,
                "quick_shown": bool(quick_text),
                "engine_note": dict(engine_state), "hypothetical": dict(hypo_state), "move_verify": dict(verify_state),
                "review": dict(review_state),
                "hedge": _hedge_state(agent),
                "answer_check": answer_check,
                "stages_ms": {**stages, "engine_ready": engine_state.get("ms"),
                              "review_ready": review_state.get("ms"),
                              "total": int((time.monotonic() - request_started) * 1000)},
            },
        )
        _timings_log.info(
            "turn timings %s",
            json.dumps({"turn": turn_id, "tier": route["tier"], "model": served_model,
                        "iterations": iterations, **stages,
                        "engine_ready": engine_state.get("ms"), "review_ready": review_state.get("ms"),
                        "hedge": _hedge_state(agent).get("winner"),
                        "quick_model": _reply_model(quick_reply) if two_stage else None,
                        # All from the request's arrival (latency_ms starts at the stream).
                        "total": int((time.monotonic() - request_started) * 1000)}),
        )

        # Per-student memory (CL Phase 1): reflect on the completed turn and write
        # failure memory, off the request path. Flag-gated (default OFF → nothing
        # new runs) and fully fail-open — never blocks or slows the reply.
        if config.COACH_MEMORY_WRITER:
            try:
                from src.memory_writer import schedule_memory_writer

                schedule_memory_writer(
                    user_id=user_id,
                    turn_id=turn_id,
                    user_message=body.message,
                    coach_reply=answer_text,
                    board_fen=session.board_state,
                    tool_results=list(tool_results),
                    model=served_model,
                )
            except Exception:
                logger.debug("memory writer scheduling failed", exc_info=True)

        envelope = wrap_response(answer_text, tool_results=tool_results)

        # The tools' board actions went out as each tool finished; only actions
        # written into the answer text itself are left.
        _, text_actions = extract_board_actions(answer_text)
        if text_actions:
            yield _board_frame(text_actions)

        game_results = envelope.get("game_results", [])
        if game_results:
            yield _sse({"game_results": game_results})

        # turn_id rides the final frame so the client can attach 👍/👎 feedback
        # to this completed answer (additive field — existing consumers ignore it).
        yield _sse({"done": True, "session_id": session.id, "turn_id": turn_id,
                    "active_board_id": session.active_board_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class PuzzleContextPuzzle(BaseModel):
    """One puzzle in the lesson's puzzle set. Every field is optional/best-effort
    — the client trims fields and older clients omit them entirely."""
    order_index: Optional[int] = None
    fen: Optional[str] = None
    solution_move: Optional[str] = None
    solution_line: list[str] = Field(default_factory=list)
    hint_text: Optional[str] = None
    source_name: Optional[str] = None
    completed: Optional[bool] = None
    attempts: Optional[int] = None

    model_config = {"extra": "ignore"}


class PuzzleContext(BaseModel):
    """Full puzzle grounding for the lesson tutor. All fields optional: older
    clients omit `puzzle_context` and the tutor still answers, just with less
    grounding. `mode` is 'multi' (puzzle set), 'single' (one-exercise lesson),
    or 'none'."""
    mode: Optional[str] = None
    current_index: Optional[int] = None
    total_count: Optional[int] = None
    current_puzzle: Optional[PuzzleContextPuzzle] = None
    current_board_fen: Optional[str] = None
    puzzles: list[PuzzleContextPuzzle] = Field(default_factory=list)

    model_config = {"extra": "ignore"}


class LessonChatRequest(BaseModel):
    """Request body for the Learning-section tutor chat.

    Lesson context (title + content) and the prior conversation are supplied by
    the caller (the Next.js proxy, which owns Supabase persistence) — Hermes
    holds no lesson state of its own. `puzzle_context` (optional) carries the
    lesson's puzzle set plus the student's live position so the tutor can answer
    questions about the exact puzzle in front of them.
    """
    message: str
    lesson_title: str = ""
    lesson_content: str = ""
    history: list[dict] = Field(default_factory=list)
    locale: str = "ru"
    puzzle_context: Optional[PuzzleContext] = None


# Cap how many puzzles we render into the prompt to keep it a sane size.
_MAX_PUZZLES_IN_PROMPT = 50


def _truncate_field(text: Optional[str], limit: int = 240) -> str:
    """Trim a free-text field so a single long hint can't blow up the prompt."""
    if not text:
        return ""
    text = str(text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _uci_line_to_readable(fen: Optional[str], line: list[str]) -> str:
    """Best-effort render of a UCI solution line as SAN; fall back to raw UCI on
    any error (illegal move, bad FEN, missing chess lib) so the tutor never gets
    a misleading line."""
    if not line:
        return ""
    if not fen:
        return " ".join(line)
    try:
        import chess

        board = chess.Board(fen)
        sans: list[str] = []
        for uci in line:
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                return " ".join(line)
            sans.append(board.san(move))
            board.push(move)
        return " ".join(sans)
    except Exception:
        return " ".join(line)


def _format_puzzle_line(p: "PuzzleContextPuzzle") -> str:
    """One-line summary of a puzzle for the 'PUZZLE SET' listing."""
    idx = p.order_index if p.order_index is not None else "?"
    parts = [f"  #{idx}"]
    if p.fen:
        parts.append(f"FEN: {p.fen}")
    line_txt = _uci_line_to_readable(p.fen, p.solution_line) or (p.solution_move or "")
    if line_txt:
        parts.append(f"solution: {line_txt}")
    if p.hint_text:
        parts.append(f"hint: {_truncate_field(p.hint_text)}")
    if p.source_name:
        parts.append(f"source: {_truncate_field(p.source_name, 80)}")
    if p.completed is not None:
        parts.append(f"completed: {'yes' if p.completed else 'no'}")
    return " | ".join(parts)


def _build_puzzle_context_section(pc: "PuzzleContext") -> str:
    """Render a clearly delimited puzzle-grounding section for the system prompt.
    Returns "" when there is nothing useful to add."""
    if pc is None or (pc.mode in (None, "none") and not pc.puzzles and not pc.current_puzzle):
        return ""

    lines: list[str] = ["\n\n=== PUZZLE CONTEXT (do not reveal verbatim) ==="]

    if pc.puzzles:
        total = pc.total_count if pc.total_count is not None else len(pc.puzzles)
        shown = pc.puzzles[:_MAX_PUZZLES_IN_PROMPT]
        lines.append(f"\nPUZZLE SET FOR THIS LESSON ({total} total):")
        for p in shown:
            lines.append(_format_puzzle_line(p))
        if len(pc.puzzles) > len(shown):
            lines.append(f"  …and {len(pc.puzzles) - len(shown)} more (omitted to keep prompt size sane).")

    cur = pc.current_puzzle
    if cur is not None:
        lines.append("\nSTUDENT'S CURRENT PUZZLE:")
        if pc.current_index is not None:
            total = pc.total_count if pc.total_count is not None else "?"
            lines.append(f"  Puzzle {pc.current_index} of {total}")
        if cur.fen:
            lines.append(f"  Starting FEN: {cur.fen}")
        sol = _uci_line_to_readable(cur.fen, cur.solution_line) or (cur.solution_move or "")
        if sol:
            lines.append(f"  Solution: {sol}")
        if cur.hint_text:
            lines.append(f"  Hint: {_truncate_field(cur.hint_text)}")
        if cur.attempts is not None:
            lines.append(f"  Attempts this session: {cur.attempts}")
        if cur.completed is not None:
            lines.append(f"  Completed: {'yes' if cur.completed else 'no'}")
    if pc.current_board_fen:
        lines.append(f"  Student's current board position: {pc.current_board_fen}")

    lines.append(
        "\nUse the solution to guide the student — ask leading questions and give "
        "hints first. Do NOT blurt out the full solution unless the student asks "
        "directly or has failed several times. You may answer questions about ANY "
        "puzzle in the set above, not just the current one. Note that a puzzle's "
        "theme may differ from the lesson's overall theme, so reason about each "
        "puzzle on its own terms."
    )
    return "\n".join(lines)


def _build_lesson_system_prompt(
    lesson_title: str,
    lesson_content: str,
    locale: str,
    puzzle_context: "Optional[PuzzleContext]" = None,
) -> str:
    """Tutor persona for the lesson chat: a friendly, encouraging chess tutor
    grounded in this specific lesson, answering in the student's language. When
    `puzzle_context` is present, appends a delimited section describing the
    lesson's puzzle set and the student's current puzzle/board state."""
    prompt = (
        "You are a friendly, encouraging chess tutor helping a student work "
        "through this specific lesson. Be warm, patient and clear; use concrete "
        "examples when they help. Keep the student focused on the lesson below "
        "and gently steer them back if they drift off-topic.\n\n"
        f"**Lesson: {lesson_title}**\n\n"
        f"{lesson_content}\n\n"
        f"Always reply in the student's language (locale: {locale})."
    )
    if puzzle_context is not None:
        prompt += _build_puzzle_context_section(puzzle_context)
    return prompt


def _lesson_chat_stream(
    model: str,
    system_prompt: str,
    message: str,
    history: list[dict],
    usage_out: Optional[dict] = None,
):
    """Yield reply text chunks for one lesson-tutor turn (plain streaming chat).

    Mirrors the coach's model selection (same OpenRouter client + routed model)
    but with no tool loop. Raises on any API error so the caller emits an SSE
    error frame instead of leaking the error text as a normal delta. When
    ``usage_out`` is given, the stream's final usage block is copied into it.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in history or []:
        role = m.get("role")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=2000,
        temperature=0.7,
        stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
        usage = getattr(chunk, "usage", None)
        if usage is not None and usage_out is not None:
            try:
                usage_out["usage"] = usage.model_dump()
            except Exception:
                usage_out["usage"] = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                }


@app.post("/api/lesson/chat")
async def lesson_chat(body: LessonChatRequest, request: Request):
    """Lesson tutor chat — streams the tutor's reply as SSE token events.

    Emits one `{"delta": ...}` frame per streamed chunk, then a final
    `{"done": true}`. On LLM failure a single `{"error": ...}` frame is emitted
    instead — never the raw error text as a delta.
    """
    user_id = _get_user_id(request)
    await enforce_rate_limit(request)
    analytics_tracker.track_chat(user_id, "")

    model = _resolve_model(None, body.message)
    system_prompt = _build_lesson_system_prompt(
        body.lesson_title, body.lesson_content, body.locale, body.puzzle_context
    )
    logger.info("Lesson tutor routed model: %s for message: %s", model, body.message[:80])

    loop = asyncio.get_event_loop()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _run():
            usage_out: dict = {}
            try:
                for chunk in _lesson_chat_stream(
                    model, system_prompt, body.message, body.history, usage_out
                ):
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, ("delta", chunk))
            except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error frame
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                record_openrouter_usage(usage_out, model=model, user_id=user_id, surface="lesson")
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        future = loop.run_in_executor(None, _run)

        error_exc = None
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                kind, payload = item
                if kind == "delta":
                    yield _sse({"delta": payload})
                elif kind == "error":
                    error_exc = payload
            await future
        except (asyncio.CancelledError, GeneratorExit):
            raise

        if error_exc is not None:
            logger.error("lesson chat LLM error: %s", error_exc, exc_info=True)
            diag.record(
                "lesson_chat_error",
                request_id=getattr(request.state, "request_id", None),
                message="lesson tutor LLM call failed on /api/lesson/chat",
                exc=error_exc,
                model=model,
            )
            yield _sse({"error": f"Tutor error: {error_exc}"})
            return

        yield _sse({"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class VoicePromptRequest(BaseModel):
    fen: Optional[str] = None
    locale: Optional[str] = None
    tools_available: bool = True
    session_id: Optional[str] = None   # the chat session the voice continues: its language holds


class VoiceEngineNoteRequest(BaseModel):
    fen: str


class VoiceCheckRequest(BaseModel):
    text: str                      # what the coach just said (its output transcription)
    fen: Optional[str] = None      # the board at the time
    pgn: Optional[str] = None      # the moves on the board, if a game is loaded
    question: Optional[str] = None  # the student's words (moves it quoted are not claims)


class VoiceHeartbeatRequest(BaseModel):
    user_id: str
    session_id: str
    seconds_delta: int = 0


# Short-lived cache for the voice profile fetch (the one Supabase round-trip in
# the mint path). Keyed by user, TTL'd so a burst of mints doesn't re-fetch the
# same profile. The prompt itself is rebuilt every call (cheap, in-memory) and
# the mint rate limit is enforced BEFORE the cache lookup — so caching never lets
# an extra session spawn through.
_VOICE_PROFILE_TTL = 300  # seconds (5 min): after that the copy is refreshed in the background
_VOICE_PROFILE_MAX_AGE = 3600  # seconds: older than this it is reloaded on the path
_voice_profile_cache: dict[str, tuple[float, UserProfile]] = {}
_voice_profile_lock = threading.Lock()
_voice_profile_refreshing: set = set()


def _get_voice_profile(user_id: str) -> UserProfile:
    """Return the user's profile, cached to spare a Supabase hit.

    The text turn uses it too (2026-09-29): every chat turn loaded the profile
    from Supabase on the event loop, freezing every other student's stream for
    the round trip. Callers in async handlers run it in a thread.

    A copy older than the TTL is handed out at once and refreshed in the
    background (a roundtrip to Supabase from the production host is 250–500
    ms; it used to land on one turn of every student every 5 minutes); only a
    copy older than an hour, or none, is loaded on the path. A load that
    failed is not cached: the next turn tries again.
    """
    now = time.monotonic()
    with _voice_profile_lock:
        entry = _voice_profile_cache.get(user_id)
    if entry:
        loaded_at, profile = entry
        age = now - loaded_at
        if age < _VOICE_PROFILE_TTL:
            return profile
        if age < _VOICE_PROFILE_MAX_AGE:
            _refresh_profile_in_background(user_id)
            return profile
    profile = load_user_profile(user_id)
    if not getattr(profile, "load_failed", False):
        with _voice_profile_lock:
            _voice_profile_cache[user_id] = (now, profile)
    return profile


def _refresh_profile_in_background(user_id: str) -> None:
    with _voice_profile_lock:
        if user_id in _voice_profile_refreshing:
            return
        _voice_profile_refreshing.add(user_id)

    def _refresh():
        try:
            profile = load_user_profile(user_id)
            if not getattr(profile, "load_failed", False):
                with _voice_profile_lock:
                    _voice_profile_cache[user_id] = (time.monotonic(), profile)
        finally:
            with _voice_profile_lock:
                _voice_profile_refreshing.discard(user_id)

    threading.Thread(target=_refresh, name="profile-refresh", daemon=True).start()


def clear_voice_profile_cache() -> None:
    """Empty the voice profile cache (used by tests)."""
    with _voice_profile_lock:
        _voice_profile_cache.clear()


def _forget_profile(user_id: str) -> None:
    """Drop one user's cached profile after it changes."""
    with _voice_profile_lock:
        _voice_profile_cache.pop(user_id, None)


@app.post("/api/coach/voice/prompt")
async def coach_voice_prompt(body: VoicePromptRequest, request: Request):
    """Render the single-source spoken system prompt + profile context for voice.

    The live-token route calls this at mint time so the voice prompt renders from
    the same SOUL persona + profile the text coach uses (no hand-written drift).
    Also enforces the voice token-mint rate limit — a 429 here tells the route to
    refuse to mint. The route fails soft on any *other* error (falls back to its
    hardcoded prompt), so this endpoint only needs to be correct, not defensive.
    """
    user_id = _get_user_id(request)

    # Cap voice-session spawns per user/hour (same mechanism as text, own limiter).
    # Enforced before the profile cache so a cache hit can never bypass the limit.
    await enforce_rate_limit(request, limiter=voice_token_rate_limiter)

    profile = await asyncio.to_thread(_get_voice_profile, user_id)
    profile_context = profile.to_prompt_context()
    # The language the session already speaks (asked for in text or aloud, or
    # written in): the spoken coach starts in it instead of the interface one.
    language = None
    if body.session_id:
        try:
            session = await asyncio.to_thread(session_store.get, body.session_id, user_id)
            if session is not None:
                language = _session_language(session, body.locale)
        except Exception:  # noqa: BLE001 — the mint must never wait on this
            logger.debug("voice prompt: session language failed", exc_info=True)
    # Memory blocks may hit Supabase — keep them off the event loop.
    system_prompt = await asyncio.to_thread(
        build_voice_prompt,
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=body.fen,
        locale=body.locale,
        tools_available=body.tools_available,
        language=language,
    )
    return {"system_prompt": system_prompt, "profile_context": profile_context}


@app.post("/api/coach/voice/engine-note")
async def coach_voice_engine_note(body: VoiceEngineNoteRequest, request: Request):
    """Stockfish's top moves for a board position, as one line for the live voice session.

    The browser calls this whenever the board changes during a voice session and
    passes the note into Gemini Live, so questions about the current position
    are answered without a tool round trip (see src/voice_engine_note.py).
    Same per-user limiter as voice tool calls. 422 when the FEN is not a legal
    position or the engine fails — the client simply sends no note.
    """
    _get_user_id(request)
    await enforce_rate_limit(request, limiter=voice_tool_rate_limiter)
    note = await asyncio.to_thread(engine_note, body.fen)
    if note is None:
        raise HTTPException(status_code=422, detail="position cannot be analysed")
    return note


@app.post("/api/coach/voice/check")
async def coach_voice_check(body: VoiceCheckRequest, request: Request):
    """Check a sentence the voice coach said against the board (src/answer_check.py).

    The text coach's answers are checked before the student sees them; a
    spoken sentence has been heard by the time its transcription arrives, so
    the browser sends it here and, when it is wrong on the board, tells the
    model to correct itself aloud. Returns {"issues": [...]} — empty when
    nothing checkable is wrong.
    """
    _get_user_id(request)
    await enforce_rate_limit(request, limiter=voice_tool_rate_limiter)
    from src.answer_check import CheckContext, check_sentence

    def _check() -> list:
        ctx = CheckContext.from_fens([body.fen], [body.pgn] if body.pgn else [], question=body.question or "")
        return check_sentence(body.text[:1000], ctx)

    issues = await asyncio.to_thread(_check)
    return {"issues": issues}


def _session_summary(s) -> dict:
    last = s.messages[-1] if s.messages else None
    return {
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at,
        "updated_at": last.timestamp if last else s.created_at,
        "message_count": len(s.messages),
        "board_state": s.board_state,
        "active_board_id": s.active_board_id,
        "board_count": len(s.boards),
        "preview": (last.content[:120] if last else ""),
    }


@app.get("/api/coach/sessions")
async def coach_list_sessions(request: Request):
    """List all coaching sessions for a user, newest activity first."""
    user_id = _get_user_id(request)
    # Off the event loop: a cold list loads every session of the user from
    # Supabase (13 sessions = dozens of roundtrips) and froze every stream.
    sessions = await asyncio.to_thread(session_store.list, user_id)
    summaries = [_session_summary(s) for s in sessions]
    summaries.sort(key=lambda x: x["updated_at"], reverse=True)
    return summaries


@app.post("/api/coach/sessions")
async def coach_create_session(request: Request, body: CoachSessionCreateRequest = None):
    """Create a new coaching session (with its default study board)."""
    user_id = _get_user_id(request)
    session = await asyncio.to_thread(session_store.create, user_id=user_id)
    if body and body.title:
        session.set_title(body.title)
    session.ensure_board()
    return _session_summary(session)


@app.patch("/api/coach/sessions/{session_id}")
async def coach_update_session(session_id: str, body: CoachSessionUpdateRequest, request: Request):
    """Rename a session or switch its active board."""
    user_id = _get_user_id(request)
    session = await asyncio.to_thread(session_store.get, session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if body.title is not None:
        session.set_title(body.title)
    if body.active_board_id is not None:
        try:
            session.set_active_board(body.active_board_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Board not found")
    return _session_summary(session)


@app.delete("/api/coach/sessions/{session_id}")
async def coach_delete_session(session_id: str, request: Request):
    user_id = _get_user_id(request)
    if not session_store.delete(session_id, user_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}


# ── Boards (tabs) of a session ────────────────────────────────────────


async def _get_session_or_404(session_id: str, request: Request):
    user_id = _get_user_id(request)
    # A session not in memory is loaded from Supabase — in a thread.
    session = await asyncio.to_thread(session_store.get, session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@app.get("/api/coach/sessions/{session_id}/boards")
async def coach_list_boards(session_id: str, request: Request):
    session = await _get_session_or_404(session_id, request)
    session.ensure_board()
    return {"active_board_id": session.active_board_id,
            "boards": [b.to_public() for b in session.boards]}


@app.post("/api/coach/sessions/{session_id}/boards")
async def coach_create_board(session_id: str, body: CoachBoardCreateRequest, request: Request):
    session = await _get_session_or_404(session_id, request)
    try:
        board = session.add_board(
            activate=body.activate, kind=body.kind, title=body.title or "", pgn=body.pgn or "",
            fen=body.fen, orientation=body.orientation, source=body.source, ply=body.ply,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return board.to_public()


@app.patch("/api/coach/sessions/{session_id}/boards/{board_id}")
async def coach_update_board(session_id: str, board_id: str, body: CoachBoardUpdateRequest, request: Request):
    session = await _get_session_or_404(session_id, request)
    board = session.get_board(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    try:
        if body.pgn is not None:
            board.load_pgn(body.pgn, ply=body.ply)
        elif body.fen is not None:
            board.set_fen(body.fen)
        elif body.position is not None:
            board.set_position(body.position)
        elif body.ply is not None:
            fens_ply = body.ply
            board.navigate("first")
            board.ply = 0
            for _ in range(max(0, fens_ply)):
                before = board.ply
                board.navigate("next")
                if board.ply == before:
                    break
        if body.title is not None:
            board.title = body.title.strip()[:120]
        if body.orientation is not None:
            if body.orientation not in ("white", "black"):
                raise ValueError("orientation must be 'white' or 'black'")
            board.orientation = body.orientation
        if body.annotations is not None:
            board.annotations = body.annotations
        if body.game_state is not None:
            board.game_state = body.game_state
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    session.save_board(board)
    if body.active:
        session.set_active_board(board.id)
    return board.to_public()


@app.delete("/api/coach/sessions/{session_id}/boards/{board_id}")
async def coach_delete_board(session_id: str, board_id: str, request: Request):
    session = await _get_session_or_404(session_id, request)
    if not session.remove_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    return {"deleted": board_id, "active_board_id": session.active_board_id}


@app.get("/api/coach/sessions/{session_id}/messages")
async def coach_get_messages(
    session_id: str, request: Request, limit: Optional[int] = None
):
    """Return a session's message list. Optional ?limit=N returns the last N.

    Scoped to the requesting user; 404 if the session is unknown to them.
    """
    user_id = _get_user_id(request)
    session = await asyncio.to_thread(session_store.get, session_id, user_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = session.messages
    if limit is not None and limit >= 0:
        messages = messages[-limit:] if limit > 0 else []

    return {
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                "source": getattr(m, "source", "text"),
            }
            for m in messages
        ]
    }


@app.post("/api/coach/sessions/{session_id}/messages")
async def coach_append_message(
    session_id: str, body: CoachMessageRequest, request: Request
):
    """Append a message to a session WITHOUT running an agent turn.

    Used for cross-modality memory (e.g. persisting voice transcripts). Creates
    the session if it doesn't exist, scoped to the requesting user.
    """
    user_id = _get_user_id(request)

    if body.role not in ("user", "assistant"):
        raise HTTPException(
            status_code=400, detail="role must be 'user' or 'assistant'"
        )

    session = await asyncio.to_thread(session_store.get, session_id, user_id)
    if session is None:
        # Never clobber a session owned by another user (the store is keyed by
        # id alone, so create() would overwrite it). Only create when the id is
        # genuinely free.
        if await asyncio.to_thread(session_store.get, session_id) is not None:
            raise HTTPException(status_code=404, detail="Session not found")
        session = await asyncio.to_thread(session_store.create, user_id=user_id, session_id=session_id)

    # Stamp the utterance time + turn id onto the row (migration 008 columns).
    # Fail-soft: persist_message drops these if the columns don't exist yet.
    extra = {"client_ts": body.client_ts, "turn_id": body.turn_id}
    extra = {k: v for k, v in extra.items() if v}
    session.add_message(
        body.role, body.content, source=body.source or "text", extra=extra or None
    )

    return {
        "ok": True,
        "session_id": session.id,
        "message_count": len(session.messages),
    }


# ── Game mode: the student plays against the coach ────────────────────────


def _get_game_board_or_404(session, board_id: str):
    board = session.get_board(board_id)
    if board is None or board.kind != "game" or not board.game_state:
        raise HTTPException(status_code=404, detail="Game not found")
    return board


@app.post("/api/coach/sessions/{session_id}/game")
async def coach_game_start(session_id: str, body: CoachGameStartRequest, request: Request):
    """Start a game against the coach on a new, active board of kind ``game``."""
    from src import game_mode

    session = await _get_session_or_404(session_id, request)
    loop = asyncio.get_event_loop()
    try:
        _, payload = await loop.run_in_executor(
            None, lambda: game_mode.start_game(session, body.color, body.elo, body.comment_mode))
    except game_mode.GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — engine failure
        logger.exception("game start failed")
        raise HTTPException(status_code=503, detail=f"The engine is unavailable: {exc}")
    return payload


@app.post("/api/coach/sessions/{session_id}/game/{board_id}/move")
async def coach_game_move(session_id: str, board_id: str, body: CoachGameMoveRequest, request: Request):
    """The student's move: verdict + the engine's reply, or the game's end."""
    from src import game_mode

    session = await _get_session_or_404(session_id, request)
    board = _get_game_board_or_404(session, board_id)
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, lambda: game_mode.play_move(session, board, body.move))
    except game_mode.GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("game move failed")
        raise HTTPException(status_code=503, detail=f"The engine is unavailable: {exc}")


@app.post("/api/coach/sessions/{session_id}/game/{board_id}/resign")
async def coach_game_resign(session_id: str, board_id: str, request: Request):
    from src import game_mode

    session = await _get_session_or_404(session_id, request)
    board = _get_game_board_or_404(session, board_id)
    try:
        return game_mode.resign(session, board)
    except game_mode.GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/coach/sessions/{session_id}/game/{board_id}/takeback")
async def coach_game_takeback(session_id: str, board_id: str, request: Request):
    from src import game_mode

    session = await _get_session_or_404(session_id, request)
    board = _get_game_board_or_404(session, board_id)
    try:
        return game_mode.takeback(session, board)
    except game_mode.GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/coach/sessions/{session_id}/game/{board_id}/comment")
async def coach_game_comment(session_id: str, board_id: str, body: CoachGameCommentRequest, request: Request):
    """The coach's short remark after a move or at the end — streamed like a
    chat answer (``delta`` frames, then ``done``), tool-free and fast, stored
    in the session as an assistant message so the conversation keeps it."""
    from src import game_mode
    from src.quick_reply import stream_completion

    user_id = _get_user_id(request)
    session = await _get_session_or_404(session_id, request)
    board = _get_game_board_or_404(session, board_id)
    comment_language = _session_language(session, body.locale)[0]
    messages = game_mode.comment_prompt(board, comment_language, body.event)
    model = quick_model()
    loop = asyncio.get_event_loop()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def _on_delta(text):
            if text:
                loop.call_soon_threadsafe(queue.put_nowait, text)

        def _run():
            try:
                return stream_completion(
                    model=model, api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                    messages=messages, on_delta=_on_delta, timeout_s=12.0, max_tokens=160,
                    temperature=0.5,
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        future = loop.run_in_executor(None, _run)
        parts: list[str] = []
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            parts.append(item)
            yield _sse({"delta": item})
        reply = await future
        text = "".join(parts).strip()
        if reply is not None and reply.error and not text:
            log_event("llm_error", severity="warn", surface="game", user_id=user_id, session_id=session.id,
                      model=model, ok=False, error_code=str(reply.error)[:80],
                      payload={"path": "game/comment"})
            yield _sse({"error": _student_error_text(comment_language)})
            return
        if reply is not None and (reply.prompt_tokens or reply.completion_tokens):
            threading.Thread(
                target=_do_record_usage,
                args=(user_id, session.id, model, reply.prompt_tokens, reply.completion_tokens, "game", None, 0),
                daemon=True,
            ).start()
        if text:
            session.add_message("assistant", text, source="game")
        yield _sse({"done": True, "session_id": session.id, "board_id": board.id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/coach/import-url")
async def coach_import_url(body: CoachImportUrlRequest, request: Request):
    """A game by its Lichess / Chess.com link — for the web page's paste path.

    The page loads the returned PGN on the board itself (no model turn), the
    same way a pasted PGN is handled. 400 for a link that is not a game or a
    game that cannot be fetched, 502 when the site is unreachable.
    """
    _get_user_id(request)
    from src.tools.game_url import GameUrlError, fetch_game_by_url

    url = (body.url or "").strip()
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fetch_game_by_url, url)
    except GameUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — network / upstream failure
        logger.info("import-url failed for %s: %s", url[:120], exc)
        raise HTTPException(status_code=502, detail="Could not reach the site the link points to.")


@app.post("/api/coach/feedback")
async def coach_feedback(body: CoachFeedbackRequest, request: Request):
    """Record an explicit 👍/👎 on a coach answer — **LOG-ONLY** signal.

    Stored for later analysis; never read in the serving path and never alters
    prompts, routing, memory, or rewards. Fail-open: a Supabase outage still
    returns 200 ``{persisted: false}`` after spooling the feedback event, and
    the endpoint never 500s on a sink failure (it must not block or slow a turn).

    ``rating 1|-1`` UPSERTs the verdict on ``(user_id, turn_id)``; ``rating 0``
    is a retraction that DELETEs the row.
    """
    user_id = _get_user_id(request)

    # Light abuse guard: cap the overall body (comment is the only growable field).
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > 8192:
                raise HTTPException(status_code=400, detail="body too large")
        except ValueError:
            pass

    turn_id = (body.turn_id or "").strip()
    if not turn_id or len(turn_id) > 64:
        raise HTTPException(status_code=400, detail="turn_id required (<=64 chars)")
    if body.rating not in (-1, 0, 1):
        raise HTTPException(status_code=400, detail="rating must be 1, -1, or 0")

    surface = body.surface or "text"
    if surface not in ("text", "voice", "review"):
        raise HTTPException(status_code=400, detail="invalid surface")

    comment = body.comment
    if comment is not None:
        # Abuse guard: reject absurdly long comments pre-truncation, then cap the
        # rest to the persisted length (see coach_feedback.COMMENT_MAX).
        if len(comment) > 2000:
            raise HTTPException(status_code=400, detail="comment too long")
        comment = comment[:500]

    # rating 0 = retraction (DELETE); 1|-1 = UPSERT the verdict. Both best-effort.
    if body.rating == 0:
        persisted = delete_feedback(user_id, turn_id)
    else:
        persisted = upsert_feedback(
            user_id,
            turn_id,
            body.rating,
            session_id=body.session_id,
            comment=comment,
            surface=surface,
            client_ts=body.client_ts,
        )

    # Dual-sink event (spool + coach_events). No comment text in the payload —
    # only whether one was present (sycophancy guard: thumbs are a signal, never
    # a training reward, and free-text must not leak into the event stream).
    log_event(
        "feedback",
        surface=surface,
        user_id=user_id,
        session_id=body.session_id,
        turn_id=turn_id,
        payload={
            "rating": body.rating,
            "surface": surface,
            "has_comment": bool(comment),
        },
    )

    return {"ok": True, "persisted": persisted}


# ── /api/coach/analysis* routes ────────────────────────────────────────
#
# These mirror the Flask /api/chat/analysis contract (backend/api/chat.py) so
# the frontend can swap its base path drop-in. A Hermes "session" IS the
# conversation, so `conversation_id` maps 1:1 onto a session id. They reuse the
# existing agentic loop, session persistence, rate limiter, and board-analysis
# injection — no parallel LLM path.


def _validate_analysis_body(data: Optional[dict]):
    """Validate an analysis request body against the Flask contract.

    Returns (fen, query, conversation_id, context_type) on success, or a
    JSONResponse (400) to return directly on failure.
    """
    if not data or "fen" not in data or "query" not in data:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Missing required fields: fen, query"},
        )
    fen = data["fen"]
    query = (data.get("query") or "").strip()
    conversation_id = data.get("conversation_id")
    context_type = data.get("context_type", "analysis")

    if not query:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Query cannot be empty"},
        )
    if len(query) > 2000:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Query too long (max 2000 characters)"},
        )
    return fen, query, conversation_id, context_type


def _check_analysis_rate_limit(request: Request, user_id: str):
    """Enforce the per-user rate limit for analysis calls.

    Returns the limiter info dict when allowed, or a JSONResponse (429) matching
    the Flask contract ({"success": false, "error": ..., "rate_limited": true}).
    """
    tier = get_user_tier(request)
    allowed, info = rate_limiter.check(user_id, tier)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": (
                    f"Rate limit exceeded for {tier} tier. "
                    f"Limit: {info['limit']} requests per minute."
                ),
                "rate_limited": True,
            },
        )
    return info


def _resolve_analysis_session(user_id: str, conversation_id: Optional[str]):
    """Reuse an owned conversation or create a new one.

    Returns the session, or a JSONResponse (404) if a conversation_id was given
    that the user does not own.
    """
    if conversation_id:
        session = session_store.get(conversation_id, user_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Conversation not found or access denied",
                },
            )
        return session
    return session_store.create(user_id=user_id)


def _prepare_analysis_turn(session, fen: str, query: str):
    """Set the board, record the user message, and build the agent inputs.

    Returns (agent, augmented_message). The system prompt is built with the FEN
    so the <board_analysis> tactical context is auto-injected.
    """
    if fen:
        try:
            session.set_board_state(fen)
        except ValueError:
            pass  # ignore invalid FEN, keep existing board state

    session.add_message("user", query)

    profile = load_user_profile(session.user_id)
    system_prompt = build_system_prompt(
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=session.board_state,
    )
    model = _resolve_model(None, query)

    # Prepend recent conversation history (excluding the just-added user message)
    # so multi-turn analysis threads keep context — mirrors coach_chat.
    history_messages = session.messages[:-1]
    if history_messages:
        recent = history_messages[-20:]
        history_text = "\n".join(f"[{m.role}]: {m.content}" for m in recent)
        augmented = (
            f"Previous conversation:\n{history_text}\n\nCurrent message:\n{query}"
        )
    else:
        augmented = query

    agent = _create_agent(
        model=model, system_prompt=system_prompt, session_id=session.id,
        user_query=query, fallback_model=_turn_fallback_model(model),
    )
    return agent, augmented


async def _stream_agent_tokens(agent, message: str):
    """Run agent.chat in an executor, bridging its token callback to the loop.

    Yields ("delta", text) as tokens arrive, then a terminal ("result", text)
    or ("error", message). Reuses the same queue-bridge pattern as coach_chat.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    sentinel = object()

    def _on_delta(text):
        if text:
            loop.call_soon_threadsafe(queue.put_nowait, ("delta", text))

    def _run():
        try:
            result = agent.chat(message, stream_callback=_on_delta)
            loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
        except Exception as exc:  # noqa: BLE001 — surfaced as a terminal item
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    future = loop.run_in_executor(None, _run)
    while True:
        item = await queue.get()
        if item is sentinel:
            break
        yield item
    await future  # ensure the executor thread has fully unwound


@app.post("/api/coach/analysis")
async def coach_analysis(request: Request):
    """Non-streaming position/game analysis — mirrors Flask /api/chat/analysis."""
    user_id = _get_user_id(request)

    try:
        data = await request.json()
    except Exception:
        data = None

    validated = _validate_analysis_body(data)
    if isinstance(validated, JSONResponse):
        return validated
    fen, query, conversation_id, _context_type = validated

    limited = _check_analysis_rate_limit(request, user_id)
    if isinstance(limited, JSONResponse):
        return limited
    usage_info = limited

    session = await asyncio.to_thread(_resolve_analysis_session, user_id, conversation_id)
    if isinstance(session, JSONResponse):
        return session

    agent, augmented = await asyncio.to_thread(_prepare_analysis_turn, session, fen, query)

    loop = asyncio.get_event_loop()
    try:
        response_text = await loop.run_in_executor(None, agent.chat, augmented)
    except Exception as exc:
        logger.error("Analysis agent error: %s", exc, exc_info=True)
        diag.record(
            "agent_error",
            request_id=getattr(request.state, "request_id", None),
            message="analysis agent.chat raised",
            exc=exc,
            path="/api/coach/analysis",
        )
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Agent error: {exc}"},
        )

    if not response_text:
        diag.record(
            "empty_response",
            request_id=getattr(request.state, "request_id", None),
            level="warning",
            message="analysis agent returned empty text; served fallback",
            path="/api/coach/analysis",
        )
        response_text = "I wasn't able to generate a response. Please try again."

    # Record real token usage for this turn (fire-and-forget; never blocks/raises)
    _record_turn_usage(
        agent, user_id, session.id, getattr(agent, "model", "unknown"),
        surface=_context_type,
    )

    session.add_message("assistant", response_text)
    tokens_used = len(response_text) // 4

    return {
        "success": True,
        "response": response_text,
        "conversation_id": session.id,
        "tokens_used": tokens_used,
        "usage": {
            "hourly_remaining": usage_info["remaining"],
            "daily_remaining": usage_info["remaining"],
            "tier": usage_info["tier"],
        },
    }


@app.post("/api/coach/analysis/stream")
async def coach_analysis_stream(request: Request):
    """Streaming position/game analysis — mirrors Flask /api/chat/analysis/stream.

    Emits `{"delta": ...}` per token, then a final
    `{"done": true, "conversation_id": ..., "tokens_used": ...}`. On failure a
    single `{"error": ...}` frame is emitted instead of the trailing done event.
    """
    user_id = _get_user_id(request)

    try:
        data = await request.json()
    except Exception:
        data = None

    validated = _validate_analysis_body(data)
    if isinstance(validated, JSONResponse):
        return validated
    fen, query, conversation_id, _context_type = validated

    limited = _check_analysis_rate_limit(request, user_id)
    if isinstance(limited, JSONResponse):
        return limited

    session = await asyncio.to_thread(_resolve_analysis_session, user_id, conversation_id)
    if isinstance(session, JSONResponse):
        return session

    agent, augmented = await asyncio.to_thread(_prepare_analysis_turn, session, fen, query)

    async def event_stream():
        streamed_any = False
        result_text = None
        error_msg = None

        async for kind, payload in _stream_agent_tokens(agent, augmented):
            if kind == "delta":
                streamed_any = True
                yield _sse({"delta": payload})
            elif kind == "result":
                result_text = payload
            elif kind == "error":
                error_msg = payload

        if error_msg is not None:
            yield _sse({"error": f"Agent error: {error_msg}"})
            return

        response_text = (
            result_text or "I wasn't able to generate a response. Please try again."
        )

        # If no tokens streamed (tool-only turn / no callback support), emit the
        # full text once so concatenated deltas reconstruct the whole message.
        if not streamed_any:
            yield _sse({"delta": response_text})

        # Record real token usage for this turn (fire-and-forget; never blocks)
        _record_turn_usage(
            agent, user_id, session.id, getattr(agent, "model", "unknown"),
            surface=_context_type,
        )

        session.add_message("assistant", response_text)
        tokens_used = len(response_text) // 4

        yield _sse(
            {
                "done": True,
                "conversation_id": session.id,
                "tokens_used": tokens_used,
            }
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/coach/history/{conversation_id}")
async def coach_history(conversation_id: str, request: Request):
    """Return a conversation's messages — mirrors Flask /api/chat/history/<id>.

    Thin wrapper over the same session persistence used by
    /api/coach/sessions/{id}/messages; 404 if the user does not own it.
    """
    user_id = _get_user_id(request)
    session = await asyncio.to_thread(session_store.get, conversation_id, user_id)
    if session is None:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "Conversation not found or access denied",
            },
        )

    updated_at = (
        session.messages[-1].timestamp if session.messages else session.created_at
    )
    return {
        "success": True,
        "conversation": {
            "id": session.id,
            "type": "analysis",
            "created_at": session.created_at,
            "updated_at": updated_at,
        },
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in session.messages
        ],
    }


@app.get("/api/coach/profile")
async def coach_get_profile(request: Request):
    """Get the user's coaching profile."""
    user_id = _get_user_id(request)
    profile = await asyncio.to_thread(_get_voice_profile, user_id)
    return profile.model_dump()


@app.put("/api/coach/profile")
async def coach_update_profile(request: Request):
    """Update the user's coaching profile."""
    user_id = _get_user_id(request)
    body = await request.json()
    profile = UserProfile(
        user_id=user_id,
        rating=body.get("rating", 1200),
        goals=body.get("goals", []),
        preferred_openings=body.get("preferred_openings", []),
        weaknesses=body.get("weaknesses", []),
        style=body.get("style", "unknown"),
    )
    save_user_profile(profile)
    _forget_profile(user_id)
    return profile.model_dump()


# ── Cost monitoring endpoint ───────────────────────────────────────────


@app.get("/api/coach/usage")
async def coach_usage(request: Request):
    """Get LLM token usage breakdown for the current user."""
    user_id = _get_user_id(request)
    return cost_monitor.get_user_usage(user_id)


# ── Voice latency metrics ingest ───────────────────────────────────────


@app.post("/api/coach/metrics")
async def coach_metrics(request: Request):
    """Ingest a voice-latency beacon from the coach client.

    Best-effort: bad fields are clamped or dropped and the endpoint always
    returns 204 (never a 5xx), so a broken beacon never disrupts the client.
    """
    user_id = _get_user_id(request)  # match the other /api/coach/* endpoints

    raw = await request.body()
    if raw and len(raw) <= MAX_BODY_BYTES:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            payload = None
        record_metric(payload)  # JSONL telemetry (unchanged)

        # Session-lifecycle metering: on the `end` beacon, record one voice
        # session row (with duration) into token_usage. Uses the sanitized
        # record so the sessionId/session_ms are already validated & clamped.
        record = sanitize_metric(payload)
        if record is not None and record.get("event") == "end":
            record_voice_event(
                user_id,
                record.get("sessionId"),
                duration_ms=record.get("session_ms"),
            )
        elif record is not None and record.get("event") == "usage":
            record_voice_usage(
                user_id,
                record.get("sessionId"),
                prompt_tokens=int(record.get("prompt_tokens") or 0),
                completion_tokens=int(record.get("completion_tokens") or 0),
                cached_tokens=int(record.get("cached_tokens") or 0),
                model=record.get("model"),
                turn_id=record.get("turn_id"),
            )

        # Phase 2: also persist the beacon to coach_events (same taxonomy as the
        # text loop). Fail-open — an event-log error must never 500 the endpoint,
        # and each request maps at most one beacon so nothing is double-logged.
        try:
            evt = beacon_to_event(payload, user_id)
            if evt is not None:
                log_event(**evt)
        except Exception:  # pragma: no cover - defensive: telemetry never 5xx
            logger.debug("coach_events beacon mapping failed", exc_info=True)

    return Response(status_code=204)


# ── Voice minutes quota ledger ─────────────────────────────────────────
# Internal routes (called only by the Next.js coach proxies, which resolve the
# user server-side). Voice Mode is metered by minutes per calendar month; text
# chat is unlimited. Auth mirrors the rest of Hermes: the shared API key when
# one is configured (no-op otherwise), plus a required user identity.


@app.post("/internal/voice/heartbeat")
async def voice_heartbeat(body: VoiceHeartbeatRequest, request: Request):
    """Accumulate a live session's spoken seconds into the voice ledger.

    Idempotent-ish: a single heartbeat delta is capped at 120s server-side so a
    replayed/bad beacon can't inflate usage. Never raises on a storage failure —
    the ledger falls back to its in-memory store and logs a warning.
    """
    _verify_api_key(request)
    voice_quota_ledger.record_heartbeat(
        body.user_id, body.session_id, body.seconds_delta
    )
    return {"ok": True}


@app.get("/internal/voice/quota")
async def voice_quota(
    request: Request, user_id: str, tier: str = DEFAULT_TIER, enforce: bool = False
):
    """Return the user's monthly voice quota state for ``tier``.

    ``{limit_seconds, used_seconds, remaining_seconds, month_key, unlimited}``.
    ``limit_seconds``/``remaining_seconds`` are ``None`` when the tier is
    unlimited. Reads degrade to the in-memory fallback on a Supabase error.

    ``enforce=true`` marks this as the mint enforcement check: when the user is
    out of minutes a ``quota_exhausted`` coach event is emitted (Phase 2). Plain
    display reads (``enforce`` absent) never emit, so the event isn't spammed.
    """
    _verify_api_key(request)
    quota = voice_quota_ledger.get_quota(user_id, tier)
    if enforce:
        voice_quota_ledger.check_exhausted(user_id, tier, quota=quota)
    return quota


# ── Analytics endpoint ─────────────────────────────────────────────────


@app.get("/api/coach/analytics")
async def coach_analytics(request: Request):
    """Get usage analytics (admin: all users, user: own data).

    Aggregated from Supabase (coach_events / token_usage / voice_usage) rather
    than process memory, so a Hermes restart no longer resets the numbers. The
    admin result is memoised for 60s to survive dashboard refresh loops. Fetches
    run off the event loop; a Supabase hiccup yields empty aggregates, never a
    5xx.
    """
    user_id = _get_user_id(request)
    if request.headers.get("x-admin") == "true":
        if not _is_admin_request(request):
            raise HTTPException(status_code=403, detail="Admin scope requires a valid admin token")
        return await asyncio.to_thread(get_admin_analytics_cached)
    return await asyncio.to_thread(compute_user_analytics, user_id)


# ── Billing endpoints ─────────────────────────────────────────────────


@app.post("/api/coach/create-checkout-session")
async def coach_create_checkout(body: CheckoutRequest, request: Request):
    """Create a Whop checkout URL for subscription."""
    user_id = _get_user_id(request)
    await enforce_rate_limit(request)

    kwargs = {"user_id": user_id, "tier": body.tier}
    if body.redirect_url:
        kwargs["redirect_url"] = body.redirect_url

    result = create_checkout_session(**kwargs)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/coach/subscription-status")
async def coach_subscription_status(request: Request):
    """Get current subscription status for the user."""
    user_id = _get_user_id(request)
    info = get_subscription_status(user_id)
    return info.model_dump()


@app.post("/api/coach/whop-webhook")
async def whop_webhook(request: Request):
    """Handle Whop webhook events (signature-verified, like the Next.js webhook)."""
    payload = await request.body()
    verdict = verify_whop_signature(
        payload,
        request.headers.get("x-whop-signature"),
        os.environ.get("WHOP_WEBHOOK_SECRET", ""),
    )
    if verdict == "no_secret":
        logger.error("whop webhook rejected: WHOP_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    if verdict != "ok":
        raise HTTPException(status_code=401, detail=f"Invalid webhook signature ({verdict})")
    result = handle_webhook_event(payload)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def main():
    """Entry point for running the server."""
    port = get_port(_config)
    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        workers=1,
    )


if __name__ == "__main__":
    main()
