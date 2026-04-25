"""Hermes Chess Coach — FastAPI server.

Exposes an OpenAI-compatible /v1/chat/completions endpoint
backed by Hermes AIAgent with the chess coach persona.
"""

import logging
import os
import shutil
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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
from src.middleware.response_envelope import wrap_response
from src.middleware.rate_limiter import enforce_rate_limit, rate_limiter
from src.middleware.circuit_breaker import stockfish_circuit, supabase_circuit
from src.model_router import route_model
from src.prompt_builder import build_system_prompt
from src.sessions import session_store
from src.user_profile import load_user_profile, save_user_profile, UserProfile
from src.cost_monitor import cost_monitor
from src.analytics import analytics_tracker
from src.billing import (
    create_checkout_session,
    get_subscription_status,
    handle_webhook_event,
)

# Load env vars before anything else
load_env()

# Set HERMES_HOME so the agent picks up the chess coach profile
os.environ.setdefault("HERMES_HOME", str(PROFILE_DIR))

# Structured logging
logger = logging.getLogger("hermes.server")

# Discover and register chess tools with the Hermes tool registry
from src.tools import discover_and_register
_loaded_tools = discover_and_register()
logger.info("Registered %d chess tool modules", len(_loaded_tools))

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
    yield


app = FastAPI(title="Hermes Chess Coach", version="1.0.0", lifespan=lifespan)


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


def _create_agent(model: str, system_prompt: str, session_id: Optional[str] = None):
    """Create a Hermes AIAgent configured for chess coaching."""
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

    return agent


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

    # If there's conversation history, prepend it as context
    if len(body.messages) > 1:
        history = "\n".join(
            f"[{m.role}]: {m.content}" for m in body.messages[:-1]
        )
        user_message = f"Previous conversation:\n{history}\n\nCurrent message:\n{user_message}"

    agent = _create_agent(
        model=model, system_prompt=system_prompt, session_id=session_id,
    )

    # Run the agent in a thread to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    try:
        response_text = await loop.run_in_executor(None, agent.chat, user_message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}")

    if not response_text:
        response_text = "I wasn't able to generate a response. Please try again."

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


class CheckoutRequest(BaseModel):
    tier: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


def _get_user_id(request: Request) -> str:
    """Extract user ID from X-User-Id header (required)."""
    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return user_id


@app.post("/api/coach/chat")
async def coach_chat(body: CoachChatRequest, request: Request):
    """Coach chat endpoint — accepts message, optional FEN and session_id."""
    user_id = _get_user_id(request)

    # Rate limiting
    await enforce_rate_limit(request)

    # Analytics
    analytics_tracker.track_chat(user_id, body.session_id or "")

    session_id = body.session_id or str(uuid.uuid4())
    session = session_store.get(session_id, user_id)
    if session is None:
        session = session_store.create(user_id=user_id, session_id=session_id)

    session.add_message("user", body.message)

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
    model = _resolve_model(None, body.message)
    logger.info("Model routed: %s for message: %s", model, body.message[:80])

    # Build conversation context from session history (exclude the just-added user message)
    history_messages = session.messages[:-1]
    if history_messages:
        recent = history_messages[-20:]  # last ~10 turns
        history_text = "\n".join(f"[{m.role}]: {m.content}" for m in recent)
        augmented_message = f"Previous conversation:\n{history_text}\n\nCurrent message:\n{body.message}"
    else:
        augmented_message = body.message

    agent = _create_agent(model=model, system_prompt=system_prompt, session_id=session_id)

    # Capture tool results for board action extraction
    tool_results: list[str] = []

    def _on_tool_complete(tool_call_id, tool_name, args, result):
        logger.info("Tool called: %s args=%s result=%s", tool_name, str(args)[:200], str(result)[:200])
        tool_results.append(result)

    agent.tool_complete_callback = _on_tool_complete

    loop = asyncio.get_event_loop()
    try:
        response_text = await loop.run_in_executor(None, agent.chat, augmented_message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent error: {exc}")

    if not response_text:
        response_text = "I wasn't able to generate a response. Please try again."

    session.add_message("assistant", response_text)
    envelope = wrap_response(response_text, tool_results=tool_results)

    return {
        "message": envelope["message"],
        "board_actions": envelope.get("board_actions", []),
        "game_results": envelope.get("game_results", []),
        "session_id": session.id,
    }


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


# ── Analytics endpoint ─────────────────────────────────────────────────


@app.get("/api/coach/analytics")
async def coach_analytics(request: Request):
    """Get usage analytics (admin: all users, user: own data)."""
    user_id = _get_user_id(request)
    # If admin header present, return global analytics
    if request.headers.get("x-admin") == "true":
        return analytics_tracker.get_analytics()
    return analytics_tracker.get_analytics(user_id=user_id)


# ── Billing endpoints ─────────────────────────────────────────────────


@app.post("/api/coach/create-checkout-session")
async def coach_create_checkout(body: CheckoutRequest, request: Request):
    """Create a Stripe Checkout Session for subscription."""
    user_id = _get_user_id(request)
    await enforce_rate_limit(request)

    kwargs = {"user_id": user_id, "tier": body.tier}
    if body.success_url:
        kwargs["success_url"] = body.success_url
    if body.cancel_url:
        kwargs["cancel_url"] = body.cancel_url

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


@app.post("/api/coach/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    result = handle_webhook_event(payload, sig_header)
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
