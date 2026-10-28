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

import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

import chess
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from src import config
from src.board_protocol import GAME_ACTION, ActionType, GAME_VIEW_ACTION
from src.cost_monitor import record_voice_event
from src.event_logger import log_event
from src.middleware.rate_limiter import enforce_rate_limit, voice_tool_rate_limiter
from src.session_persistence import SessionLoadError
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

_BOARD_ACTION_TYPES = frozenset({e.value for e in ActionType} | {GAME_ACTION, GAME_VIEW_ACTION})  # game_view: the voice path kept dropping it (prod, 26.10)


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
    """Return board-action dicts embedded in a parsed tool result: the result
    itself (board_control), a list of them, or a ``board_actions`` list carried
    next to the data (get_topic's example, get_lesson's exercise)."""
    actions: list[dict] = []
    candidates = result if isinstance(result, list) else [result]
    if isinstance(result, dict) and isinstance(result.get("board_actions"), list):
        candidates = result["board_actions"]
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
            board = session.get_board(session.active_board_id)
            if board is not None:
                board.mark_coach(str(atype))  # a tool's position, not the student's own (2026-10-20)
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


def _classify_tool_result(name: str, args: dict, raw: Any) -> tuple[bool, Optional[str], dict]:
    """Build (ok, error_code, payload) for a voice ``tool_call`` coach event.

    Mirrors the text loop's ``_tool_call_payload`` (server.py): parses the result
    to classify success/failure, truncates args + a result summary, and folds in
    the ``check_moves`` legal/illegal verdict (the hallucination metric).
    """
    parsed = None
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        parsed = None

    ok = True
    error_code: Optional[str] = None
    if isinstance(parsed, dict) and "error" in parsed:
        ok = False
        err = parsed.get("error")
        if isinstance(err, dict):
            error_code = str(err.get("type") or err.get("message") or "error")[:100]
        else:
            error_code = str(err)[:100]

    payload: dict = {
        "args": str(args)[:500],
        "result_summary": str(raw)[:500],
    }
    if name == "check_moves" and isinstance(parsed, dict):
        results = parsed.get("results")
        if isinstance(results, list):
            legal = sum(1 for r in results if isinstance(r, dict) and r.get("legal") is True)
            payload["check_moves_verdict"] = {
                "candidates": len(results),
                "legal": legal,
                "illegal": len(results) - legal,
            }
    return ok, error_code, payload


def dispatch_tool_safely(name: str, args: dict, **kwargs) -> str:
    """Dispatch a tool, converting any raised exception into a structured error.

    ``registry.dispatch`` already catches most handler exceptions and returns a
    JSON error string, but a malformed call (or a bug outside the handler) can
    still raise. This outer guard ensures such a failure yields a recoverable
    error envelope the model can act on rather than an unhandled 500. Successful
    dispatch is returned verbatim — behavior is unchanged on the happy path.
    """
    try:
        return registry.dispatch(name, args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - deliberately broad, never re-raise
        logger.warning("Tool dispatch raised for %s: %s", name, exc, exc_info=True)
        return json.dumps(_tool_error_payload(name, exc))


class ToolDispatchRequest(BaseModel):
    args: dict[str, Any] = {}
    session_id: Optional[str] = None
    # The student's last words (voice): the board lock is decided from them, as the text coach's
    # turn decides it from the message (src/board_lock.py).
    utterance: Optional[str] = None


# The board lock a voice tool call runs under. Calls of one model turn come in parallel: the lock
# stays until the last of them is done (a text turn of the same session keeps its own lock).
_voice_locks: dict[str, int] = {}
_voice_locks_guard = threading.Lock()


def _dispatch_voice(name: str, args: dict, session, utterance: Optional[str]) -> str:
    """The tool in the student's coach session, under the board lock their words call for."""
    if session is None:
        return dispatch_tool_safely(name, args)
    from src.board_lock import _board_lock_level, board_lock_with_owner
    from src.tools.game_play import live_game_board

    live = live_game_board(session) is not None
    if config.COACH_HIDDEN_BOARD:
        # The student's own position stays unless their words ask for another (src/question_position).
        fen, strict, reason = board_lock_with_owner(utterance or "", True, live, session)
    else:
        fen, strict, reason = _board_lock_level(utterance or "", True, live, session.board_state)
    owned = False
    with _voice_locks_guard:
        depth = _voice_locks.get(session.id, 0)
        if fen and (depth or session.board_lock is None):
            if not depth:
                session.lock_board(fen, strict=strict, reason=reason)
            _voice_locks[session.id] = depth + 1
            owned = True
    try:
        return dispatch_tool_safely(name, args, session_id=session.id, student_message=utterance or "")
    finally:
        if owned:
            with _voice_locks_guard:
                left = _voice_locks.get(session.id, 1) - 1
                if left <= 0:
                    _voice_locks.pop(session.id, None)
                    session.lock_board(None)
                else:
                    _voice_locks[session.id] = left


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
    # The coach session (when it is the caller's): the tools see it as the text coach's do — the
    # board lock, the game on the board (src/tools/game_play.py). Before 2026-10-12 the voice
    # calls ran without it.
    session = None
    if body.session_id:
        try:
            session = await asyncio.to_thread(session_store.get, body.session_id, user_id)
        except SessionLoadError:
            raise  # the game is unknown, not absent: 503, never the tool in "no game" mode (28.10)
        except Exception:  # noqa: BLE001 — the tool still runs, without the session
            session = None
    started = time.monotonic()
    raw = await run_in_threadpool(_dispatch_voice, name, args, session, body.utterance)
    duration_ms = int((time.monotonic() - started) * 1000)

    # Persist the voice tool execution to coach_events (Phase 2, Task 3). This is
    # the authoritative record — the browser's tool beacon only surfaces calls the
    # server never executed (rate-limited / proxy failures). Fail-open.
    ok, error_code, evt_payload = _classify_tool_result(name, args, raw)
    log_event(
        "tool_call",
        severity="info" if ok else "warn",
        surface="voice",
        user_id=user_id,
        session_id=body.session_id,
        tool_name=name,
        duration_ms=duration_ms,
        ok=ok,
        error_code=error_code,
        payload=evt_payload,
    )

    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        parsed = raw

    if isinstance(parsed, dict) and "error" in parsed:
        return {"error": parsed["error"]}

    board_actions = _extract_board_actions(parsed)

    if body.session_id and board_actions:
        session = await asyncio.to_thread(session_store.get, body.session_id, user_id)
        if session is not None:
            # Arrows a piece cannot draw are dropped here as in the text turn (board_markup.prune_arrows): the
            # voice model drew «the knight d4 attacks c4» on Alexander's phone (24.10) — the text path had the
            # pruning since 01.10, the voice path returned the arrows as drawn.
            board_actions, dropped = _prune_voice_arrows(board_actions, session.board_state)
            if dropped and isinstance(parsed, dict):
                parsed = {**parsed, "arrows_dropped": dropped,
                          "arrows_note": "These arrows were NOT drawn — the piece on the square cannot move that way. "
                                         "Do not describe them as attacks or threats."}
            _sync_session_board(session, board_actions)

    return {"result": parsed, "board_actions": board_actions}


def _prune_voice_arrows(actions: list, fen: Optional[str]) -> tuple[list, list]:
    """(the actions with impossible arrows removed, the arrows removed as 'd4c4: a knight cannot go there')."""
    from src.board_markup import prune_arrows

    kept, dropped = [], []
    for action in actions:
        if not isinstance(action, dict) or action.get("type") != "draw_arrows" or not fen:
            kept.append(action)
            continue
        pruned = prune_arrows(action, fen)
        left = {(a.get("from"), a.get("to")) for a in (pruned.get("arrows") or [])} if pruned else set()
        try:
            board = chess.Board(fen)
        except ValueError:
            board = None
        for arrow in action.get("arrows") or []:
            if (arrow.get("from"), arrow.get("to")) in left:
                continue
            piece = board.piece_at(chess.parse_square(str(arrow.get("from")))) if board else None
            what = chess.piece_name(piece.piece_type) if piece else "piece"
            dropped.append(f"{arrow.get('from')}{arrow.get('to')}: a {what} cannot go there")
        if pruned:
            kept.append(pruned)
    return kept, dropped
