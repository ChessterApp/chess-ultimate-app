"""Hermes Chess Coach — FastAPI server.

Exposes an OpenAI-compatible /v1/chat/completions endpoint
backed by Hermes AIAgent with the chess coach persona.
"""

import json
import logging
import os
import shutil
import threading
import time
import uuid
import asyncio
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
    PROFILE_DIR,
)
# load_env() must run before importing src.sessions: the global session store
# reads SUPABASE_* at import time, and without the .env loaded persistence
# silently degrades to in-memory (sessions would not survive restarts).
load_env()

from src.middleware.response_envelope import wrap_response  # noqa: E402
from src.middleware.rate_limiter import (  # noqa: E402
    enforce_rate_limit,
    rate_limiter,
    voice_token_rate_limiter,
    get_user_tier,
    DEFAULT_TIER,
)
from src.middleware.circuit_breaker import stockfish_circuit, supabase_circuit
from src.model_router import route_model, explain_route
from src.prompt_builder import build_system_prompt, build_voice_prompt, get_prompt_version
from src.event_logger import log_event, new_turn_id
from src.coach_feedback import upsert_feedback, delete_feedback
from src import config
from src import coach_diagnostics as diag
from src.processors.text_normalize import normalize_text
from src.sessions import session_store
from src.user_profile import load_user_profile, save_user_profile, UserProfile
from src.cost_monitor import cost_monitor, record_voice_event
from src.analytics import analytics_tracker
from src.analytics_db import compute_user_analytics, get_admin_analytics_cached
from src.retention import retention_loop
from src.billing import (
    create_checkout_session,
    get_subscription_status,
    handle_webhook_event,
)
from src.voice_metrics import (
    MAX_BODY_BYTES,
    beacon_to_event,
    record_metric,
    sanitize_metric,
)
from src.voice_quota import voice_quota_ledger

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
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    app.state.config = _config
    app.state.model_config = _model_config
    app.state.soul_content = _soul_content

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

    logger.info(
        "request_start method=%s path=%s request_id=%s",
        request.method,
        request.url.path,
        request_id,
    )

    start = time.monotonic()
    response = await call_next(request)
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


def _create_agent(
    model: str,
    system_prompt: str,
    session_id: Optional[str] = None,
    user_query: Optional[str] = None,
    mode: str = "full",
):
    """Create a Hermes AIAgent configured for chess coaching.

    When ``COACH_TOOL_SUBSET`` is enabled and a ``user_query`` is provided, the
    agent's tool schemas are reduced to a query-relevant subset (mirroring the
    voice path). With the flag off or ``user_query`` None the agent is left
    untouched, so behavior is byte-identical to today.
    """
    from run_agent import AIAgent

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    agent = AIAgent(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
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

    if config.COACH_TOOL_SUBSET and user_query and getattr(agent, "tools", None):
        from src.tool_selector import select_openai_tool_subset

        agent.tools = select_openai_tool_subset(
            agent.tools,
            user_query,
            topk=config.COACH_TOOL_SUBSET_TOPK,
            mode=mode,
        )
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
        )
    except Exception:
        logger.exception("token usage recording failed")


def _record_turn_usage(
    agent,
    user_id: str,
    session_id: str,
    model: str,
    surface: str = "text",
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
    except Exception:
        return None

    if prompt_tokens <= 0 and completion_tokens <= 0:
        return None

    thread = threading.Thread(
        target=_do_record_usage,
        args=(user_id, session_id, model, prompt_tokens, completion_tokens, surface),
        daemon=True,
    )
    thread.start()
    return thread


# ── Health endpoint (enhanced) ─────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint with service status details."""
    import psutil

    process = psutil.Process()
    mem = process.memory_info()

    stockfish_available = shutil.which("stockfish") is not None or os.path.exists(
        "/usr/games/stockfish"
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
    session = session_store.get(session_id, user_id)
    if session is None:
        session = session_store.create(user_id=user_id, session_id=session_id)

    # Build the user message from the last message in the conversation
    user_message = body.messages[-1].content if body.messages else ""
    if not user_message:
        raise HTTPException(status_code=400, detail="No message content provided")

    # Hygiene: normalize inbound free-text (no-op unless COACH_NORMALIZE_INPUT)
    user_message = _clean_user_text(user_message)

    # Record user message in session
    session.add_message("user", user_message)

    # Load user profile for personalization
    profile = load_user_profile(user_id)

    # Build personalized system prompt
    system_prompt = build_system_prompt(
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

    agent = _create_agent(
        model=model, system_prompt=system_prompt, session_id=session_id,
        user_query=raw_user_query,
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


class CoachSessionCreateRequest(BaseModel):
    title: Optional[str] = None


class CoachMessageRequest(BaseModel):
    role: str
    content: str
    source: Optional[str] = None
    # Phase 2 (Task 4): true utterance timestamp (ISO8601, stamped in the browser
    # at turn completion) and the turn correlation id, so voice message rows carry
    # the spoken time — not the write time — and join to coach_events by turn_id.
    client_ts: Optional[str] = None
    turn_id: Optional[str] = None


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


@app.post("/api/coach/chat")
async def coach_chat(body: CoachChatRequest, request: Request):
    """Coach chat endpoint — streams the agent's reply as SSE token events.

    Emits, in order: one `{"delta": ...}` frame per streamed text chunk, then
    (if present) `{"board_actions": [...]}` and `{"game_results": [...]}`, and
    finally `{"done": true, "session_id": ...}`. On failure a single
    `{"error": ...}` frame is emitted instead of the trailing events.
    """
    user_id = _get_user_id(request)

    # Rate limiting
    await enforce_rate_limit(request)

    # Analytics
    analytics_tracker.track_chat(user_id, body.session_id or "")

    session_id = body.session_id or str(uuid.uuid4())
    session = session_store.get(session_id, user_id)
    if session is None:
        session = session_store.create(user_id=user_id, session_id=session_id)

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

    if body.fen:
        try:
            session.set_board_state(body.fen)
        except ValueError:
            pass  # ignore invalid FEN, use existing board state

    profile = load_user_profile(user_id)
    system_prompt = build_system_prompt(
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=session.board_state,
        locale=body.locale,
    )
    logger.info("Model routed: %s for message: %s", model, body.message[:80])

    # Build conversation context from session history (exclude the just-added user message)
    history_messages = session.messages[:-1]
    if history_messages:
        recent = history_messages[-20:]  # last ~10 turns
        history_text = "\n".join(f"[{m.role}]: {m.content}" for m in recent)
        augmented_message = f"Previous conversation:\n{history_text}\n\nCurrent message:\n{body.message}"
    else:
        augmented_message = body.message

    agent = _create_agent(
        model=model, system_prompt=system_prompt, session_id=session_id,
        user_query=body.message,
    )

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
        },
    )

    # Capture tool results for board action extraction
    tool_results: list[str] = []

    loop = asyncio.get_event_loop()

    async def event_stream():
        # Bridge the agent's synchronous, executor-thread token callback onto the
        # event loop via a thread-safe queue so tokens stream out as they arrive.
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        streamed_any = False
        # Per-turn state used by the coach_events instrumentation below.
        tool_starts: dict = {}
        partial_parts: list[str] = []
        streamed_chars = 0

        def _on_delta(text):
            if text:
                loop.call_soon_threadsafe(queue.put_nowait, ("delta", text))

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
                result = agent.chat(augmented_message, stream_callback=_on_delta)
                loop.call_soon_threadsafe(queue.put_nowait, ("result", result))
            except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error frame
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        turn_started = time.monotonic()
        future = loop.run_in_executor(None, _run)

        result_text = None
        error_exc = None
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                kind, payload = item
                if kind == "delta":
                    streamed_any = True
                    partial_parts.append(payload)
                    streamed_chars += len(payload)
                    yield _sse({"delta": payload})
                elif kind == "tool_call":
                    yield _sse({"tool_call": payload})
                elif kind == "tool_result":
                    yield _sse({"tool_result": payload})
                elif kind == "result":
                    result_text = payload
                elif kind == "error":
                    error_exc = payload
            await future  # ensure the executor thread has fully unwound
        except (asyncio.CancelledError, GeneratorExit):
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

        if error_exc is not None:
            # Streaming-path LLM failure — previously left ZERO trace. Emit the
            # event AND write a diagnostic (the streaming path never did before).
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
                error_code=type(error_exc).__name__,
                payload={"error_class": type(error_exc).__name__, "message": str(error_exc)[:2000]},
            )
            diag.record(
                "agent_error",
                request_id=getattr(request.state, "request_id", None),
                message="agent.chat raised on /api/coach/chat (streaming)",
                exc=error_exc,
                model=model,
            )
            yield _sse({"error": f"Agent error: {error_exc}"})
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
                model=model,
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
                model=model,
                payload={"path": "/api/coach/chat"},
            )

        response_text = result_text or "I wasn't able to generate a response. Please try again."

        # If the agent produced no token stream (no callback support / tool-only
        # turn), fall back to emitting the completed text as a single delta so the
        # concatenated deltas always reconstruct the full assistant message.
        if not streamed_any:
            yield _sse({"delta": response_text})

        # Record real token usage for this turn (fire-and-forget; never blocks)
        _record_turn_usage(agent, user_id, session.id, model, surface="text")

        prompt_tokens = _safe_int(getattr(agent, "session_prompt_tokens", 0)) or 0
        completion_tokens = _safe_int(getattr(agent, "session_completion_tokens", 0)) or 0

        # Stamp the assistant row with the full turn telemetry (fail-soft on
        # pre-migration prod: persist_message retries without the new columns).
        assistant_extra = {
            "turn_id": turn_id,
            "model": model,
            "prompt_version": prompt_version,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        session.add_message("assistant", response_text, extra=assistant_extra, evt=evt_ctx)

        finish_reason = "empty" if not result_text else ("max_iterations" if hit_max else "stop")
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
                "iterations": iterations,
                "finish_reason": finish_reason,
            },
        )

        envelope = wrap_response(response_text, tool_results=tool_results)

        board_actions = envelope.get("board_actions", [])
        if board_actions:
            yield _sse({"board_actions": board_actions})

        game_results = envelope.get("game_results", [])
        if game_results:
            yield _sse({"game_results": game_results})

        # turn_id rides the final frame so the client can attach 👍/👎 feedback
        # to this completed answer (additive field — existing consumers ignore it).
        yield _sse({"done": True, "session_id": session.id, "turn_id": turn_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class VoicePromptRequest(BaseModel):
    fen: Optional[str] = None
    locale: Optional[str] = None
    tools_available: bool = True


class VoiceHeartbeatRequest(BaseModel):
    user_id: str
    session_id: str
    seconds_delta: int = 0


# Short-lived cache for the voice profile fetch (the one Supabase round-trip in
# the mint path). Keyed by user, TTL'd so a burst of mints doesn't re-fetch the
# same profile. The prompt itself is rebuilt every call (cheap, in-memory) and
# the mint rate limit is enforced BEFORE the cache lookup — so caching never lets
# an extra session spawn through.
_VOICE_PROFILE_TTL = 300  # seconds (5 min)
_voice_profile_cache: dict[str, tuple[float, UserProfile]] = {}
_voice_profile_lock = threading.Lock()


def _get_voice_profile(user_id: str) -> UserProfile:
    """Return the user's profile, cached for ~5 min to spare a Supabase hit."""
    now = time.monotonic()
    with _voice_profile_lock:
        entry = _voice_profile_cache.get(user_id)
        if entry and entry[0] > now:
            return entry[1]
    profile = load_user_profile(user_id)
    with _voice_profile_lock:
        _voice_profile_cache[user_id] = (now + _VOICE_PROFILE_TTL, profile)
    return profile


def clear_voice_profile_cache() -> None:
    """Empty the voice profile cache (used by tests)."""
    with _voice_profile_lock:
        _voice_profile_cache.clear()


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

    profile = _get_voice_profile(user_id)
    profile_context = profile.to_prompt_context()
    system_prompt = build_voice_prompt(
        soul_content=_soul_content,
        user_profile=profile,
        board_fen=body.fen,
        locale=body.locale,
        tools_available=body.tools_available,
    )
    return {"system_prompt": system_prompt, "profile_context": profile_context}


@app.get("/api/coach/sessions")
async def coach_list_sessions(request: Request):
    """List all coaching sessions for a user."""
    user_id = _get_user_id(request)
    sessions = session_store.list(user_id)
    return [
        {
            "id": s.id,
            "created_at": s.created_at,
            "message_count": len(s.messages),
            "board_state": s.board_state,
        }
        for s in sessions
    ]


@app.post("/api/coach/sessions")
async def coach_create_session(request: Request, body: CoachSessionCreateRequest = None):
    """Create a new coaching session."""
    user_id = _get_user_id(request)
    session = session_store.create(user_id=user_id)
    return {
        "id": session.id,
        "created_at": session.created_at,
        "message_count": 0,
        "board_state": session.board_state,
    }


@app.get("/api/coach/sessions/{session_id}/messages")
async def coach_get_messages(
    session_id: str, request: Request, limit: Optional[int] = None
):
    """Return a session's message list. Optional ?limit=N returns the last N.

    Scoped to the requesting user; 404 if the session is unknown to them.
    """
    user_id = _get_user_id(request)
    session = session_store.get(session_id, user_id)
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

    session = session_store.get(session_id, user_id)
    if session is None:
        # Never clobber a session owned by another user (the store is keyed by
        # id alone, so create() would overwrite it). Only create when the id is
        # genuinely free.
        if session_store.get(session_id) is not None:
            raise HTTPException(status_code=404, detail="Session not found")
        session = session_store.create(user_id=user_id, session_id=session_id)

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
        user_query=query,
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

    session = _resolve_analysis_session(user_id, conversation_id)
    if isinstance(session, JSONResponse):
        return session

    agent, augmented = _prepare_analysis_turn(session, fen, query)

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

    session = _resolve_analysis_session(user_id, conversation_id)
    if isinstance(session, JSONResponse):
        return session

    agent, augmented = _prepare_analysis_turn(session, fen, query)

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
    session = session_store.get(conversation_id, user_id)
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
    profile = load_user_profile(user_id)
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
    """Handle Whop webhook events."""
    payload = await request.body()
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
