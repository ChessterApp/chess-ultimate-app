"""Voice tool bridge — expose the chess tool registry to the Gemini Live coach.

The text coach reaches the ~20 chess tools through the Hermes agent loop. The
voice coach (Gemini Live) does its own function-calling, so it needs:

  * ``GET  /api/coach/tools``        — every chess tool's schema in Gemini
                                        ``functionDeclarations`` format.
  * ``POST /api/coach/tool/{name}``  — dispatch one tool and return its result
                                        (plus any board actions it emitted).

Both endpoints are generic: the registry is the single source of truth, so no
tool schema is ever hand-copied here.
"""

import json
import logging
from typing import Any, Optional

import chess
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src import config
from src.board_protocol import ActionType
from src.cost_monitor import record_voice_event
from src.middleware.rate_limiter import enforce_rate_limit, voice_tool_rate_limiter
from src.sessions import session_store
from src.tool_selector import select_tool_subset

try:
    from tools.registry import registry
except ImportError:  # pragma: no cover - registry always present in deployment
    registry = None

logger = logging.getLogger("hermes.tool_bridge")

router = APIRouter()

CHESS_TOOLSET = "chess"

# External MCP-server tools are registered under toolsets named ``mcp-<name>``
# by the framework's discover_mcp_tools(). They're only surfaced to the coach
# when COACH_MCP_ENABLED is on (see build_tool_declarations).
MCP_TOOLSET_PREFIX = "mcp-"

# Keys that are valid JSON Schema but rejected by Gemini's function-calling
# schema (an OpenAPI 3.0 subset). Stripped recursively from every tool schema.
_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {"$schema", "additionalProperties", "default", "$ref", "definitions", "$defs"}
)

# Argument names that identify a user. The model must never be able to set
# these — they are always overridden server-side with the authenticated user.
_IDENTITY_ARG_KEYS = frozenset({"user_id"})

_BOARD_ACTION_TYPES = frozenset(e.value for e in ActionType)


def clean_gemini_schema(node: Any) -> Any:
    """Recursively strip JSON-Schema keys Gemini's function-calling rejects."""
    if isinstance(node, dict):
        return {
            key: clean_gemini_schema(value)
            for key, value in node.items()
            if key not in _UNSUPPORTED_SCHEMA_KEYS
        }
    if isinstance(node, list):
        return [clean_gemini_schema(item) for item in node]
    return node


def to_function_declaration(schema: dict, name: Optional[str] = None) -> dict:
    """Convert a registry tool schema to a Gemini functionDeclaration.

    The registry key (*name*) is authoritative — the same rule the agent's
    ``get_definitions`` uses — so a schema with a missing/blank ``name`` still
    produces a valid declaration.
    """
    parameters = clean_gemini_schema(schema.get("parameters", {}))
    return {
        "name": name or schema.get("name", ""),
        "description": schema.get("description", ""),
        "parameters": parameters,
    }


def _declaration_tool_names() -> list[str]:
    """Tool names to declare: the chess toolset, plus ``mcp-*`` when enabled.

    With ``COACH_MCP_ENABLED`` off this is exactly the chess toolset, so the
    declarations are byte-identical to the pre-Phase-2 behavior. When the flag
    is on, tools from every toolset whose name starts with ``mcp-`` are appended
    so the coach can call the off-process engine MCP tools. The flag is read via
    the config module so it reflects the current environment.
    """
    names = list(registry.get_tool_names_for_toolset(CHESS_TOOLSET))
    if config.COACH_MCP_ENABLED:
        for toolset in registry.get_registered_toolset_names():
            if toolset.startswith(MCP_TOOLSET_PREFIX):
                names.extend(registry.get_tool_names_for_toolset(toolset))
    return names


def build_tool_declarations(
    query: Optional[str] = None,
    topk: Optional[int] = None,
    mode: str = "full",
) -> list[dict]:
    """Return Gemini functionDeclarations for the coach's tools.

    Default (and whenever ``COACH_TOOL_SUBSET`` is off or no *query* is given)
    is the full toolset, byte-identical to the historical behavior. When the
    flag is on and a *query* is supplied, a query-relevant subset is selected
    (core tools always kept) to cut per-turn token payload.

    When ``COACH_MCP_ENABLED`` is on, tools from ``mcp-*`` toolsets are included
    alongside the chess tools; tool-subsetting (when enabled) then applies to
    the combined set. With the MCP flag off, only chess tools are declared.
    """
    if registry is None:
        return []
    declarations = []
    for name in _declaration_tool_names():
        if not name:
            continue
        schema = registry.get_schema(name)
        if not schema:
            continue
        declarations.append(to_function_declaration(schema, name=name))

    if not config.COACH_TOOL_SUBSET or not query:
        return declarations

    k = topk if topk is not None else config.COACH_TOOL_SUBSET_TOPK
    return select_tool_subset(declarations, query, topk=k, mode=mode)


def _is_chess_tool(name: str) -> bool:
    """True when *name* is a tool registered under the chess toolset."""
    if registry is None:
        return False
    return registry.get_toolset_for_tool(name) == CHESS_TOOLSET


def _override_identity_args(name: str, args: dict, user_id: str) -> dict:
    """Force user-identity args to the authenticated user before dispatch.

    Overrides any identity key the model supplied, and also injects the id when
    the tool's schema declares an identity param the model omitted.
    """
    safe_args = dict(args)
    schema = registry.get_schema(name) if registry else None
    declared = set()
    if isinstance(schema, dict):
        props = schema.get("parameters", {}).get("properties", {})
        if isinstance(props, dict):
            declared = set(props.keys())
    for key in _IDENTITY_ARG_KEYS:
        if key in safe_args or key in declared:
            safe_args[key] = user_id
    return safe_args


def _final_fen_from_pgn(pgn: str) -> Optional[str]:
    """Return the FEN of the final position of a PGN, or None if unparseable."""
    import io

    import chess.pgn

    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
        if game is None:
            return None
        board = game.end().board()
        return board.fen()
    except Exception:
        return None


def _extract_board_actions(result: Any) -> list[dict]:
    """Return board-action dicts embedded in a parsed tool result."""
    actions: list[dict] = []
    candidates = result if isinstance(result, list) else [result]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("type") in _BOARD_ACTION_TYPES:
            actions.append(candidate)
    return actions


def _sync_session_board(session, board_actions: list[dict]) -> None:
    """Update a session's board_state from set_fen / set_puzzle / load_pgn actions."""
    for action in board_actions:
        atype = action.get("type")
        fen = None
        if atype in (ActionType.SET_FEN.value, ActionType.SET_PUZZLE.value):
            fen = action.get("fen")
        elif atype == ActionType.LOAD_PGN.value and action.get("pgn"):
            fen = _final_fen_from_pgn(action["pgn"])
        if not fen:
            continue
        try:
            session.set_board_state(fen)
        except (ValueError, TypeError):
            logger.debug("Skipping board sync for invalid FEN: %s", fen)


def _tool_error_payload(name: str, exc: Exception) -> dict:
    """Structured, model-readable error envelope for a failed tool dispatch.

    Shaped so the LLM can recover (retry or pick another tool) instead of the
    endpoint bubbling a fatal 500. Mirrors the ``{"error": ...}`` contract the
    dispatch endpoint already returns for tool-reported errors.
    """
    return {
        "error": {
            "tool": name,
            "type": type(exc).__name__,
            "message": str(exc) or type(exc).__name__,
            "recoverable": True,
        }
    }


def dispatch_tool_safely(name: str, args: dict) -> str:
    """Dispatch a tool, converting any raised exception into a structured error.

    ``registry.dispatch`` already catches most handler exceptions and returns a
    JSON error string, but a malformed call (or a bug outside the handler) can
    still raise. This outer guard ensures such a failure yields a recoverable
    error envelope the model can act on rather than an unhandled 500. Successful
    dispatch is returned verbatim — behavior is unchanged on the happy path.
    """
    try:
        return registry.dispatch(name, args)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, never re-raise
        logger.warning("Tool dispatch raised for %s: %s", name, exc, exc_info=True)
        return json.dumps(_tool_error_payload(name, exc))


class ToolDispatchRequest(BaseModel):
    args: dict[str, Any] = {}
    session_id: Optional[str] = None


def _get_user_id(request: Request) -> str:
    """Extract the required X-User-Id header."""
    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return user_id


@router.get("/api/coach/tools")
async def coach_tools(
    q: Optional[str] = None,
    topk: Optional[int] = None,
    mode: str = "full",
) -> dict:
    """Return chess tool schemas as Gemini functionDeclarations.

    With no query params (or COACH_TOOL_SUBSET off) this returns the full
    toolset exactly as before. When the flag is on, an optional ``q`` selects a
    relevant subset; ``topk`` and ``mode`` (``full``/``panel``) tune it.
    """
    return {"tools": build_tool_declarations(query=q, topk=topk, mode=mode)}


@router.post("/api/coach/tool/{name}")
async def coach_tool_dispatch(name: str, body: ToolDispatchRequest, request: Request):
    """Dispatch a single chess tool for the voice coach.

    Returns ``{"result": ..., "board_actions": [...]}`` on success, or
    ``{"error": ...}`` (HTTP 200) when the tool fails — the voice model always
    needs a tool response, even on failure. Unknown tool -> 404. Rate limited
    per user/tier (429 when exceeded); each invocation is metered to
    ``token_usage`` with ``surface="voice"``.
    """
    user_id = _get_user_id(request)

    # Same sliding-window mechanism/tiers as text chat, on the voice-tool limiter.
    await enforce_rate_limit(request, limiter=voice_tool_rate_limiter)

    if not _is_chess_tool(name):
        raise HTTPException(status_code=404, detail=f"Unknown tool: {name}")

    # Meter the voice tool invocation (fire-and-forget). One row per call so the
    # per-session tool-call count can be reconstructed for cost estimation.
    record_voice_event(user_id, body.session_id, tool_name=name)

    args = _override_identity_args(name, body.args or {}, user_id)

    # registry.dispatch is synchronous and can block for seconds (e.g. a
    # Stockfish analysis at depth 18). Run it off the event loop so slow tools
    # don't freeze concurrent requests such as /health. dispatch_tool_safely
    # additionally converts any raised exception into a structured error
    # envelope so a malformed tool call never bubbles a fatal 500.
    raw = await run_in_threadpool(dispatch_tool_safely, name, args)

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        parsed = raw

    if isinstance(parsed, dict) and "error" in parsed:
        return {"error": parsed["error"]}

    board_actions = _extract_board_actions(parsed)

    if body.session_id and board_actions:
        session = session_store.get(body.session_id, user_id)
        if session is not None:
            _sync_session_board(session, board_actions)

    return {"result": parsed, "board_actions": board_actions}
