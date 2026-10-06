"""Configuration loader for Hermes Chess Coach."""

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = PROJECT_ROOT / "profiles" / "chess-coach"


def load_env(env_path: Path = None) -> None:
    """Load .env file from project root."""
    if env_path is None:
        env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)


# Load .env before any module-level os.environ reads below. server.py's own
# load_env() call happens after `import src.config`, which is too late for the
# flags evaluated at import time (e.g. COACH_MEMORY_WRITER stayed False even
# with COACH_MEMORY_WRITER=1 in .env).
load_env()


def load_profile_config(config_path: Path = None) -> dict:
    """Load and return the chess coach profile config.yaml with env var substitution."""
    if config_path is None:
        config_path = PROFILE_DIR / "config.yaml"
    with open(config_path) as f:
        raw = f.read()
    # Substitute ${VAR} patterns with environment variables
    expanded = _expand_env_vars(raw)
    return yaml.safe_load(expanded)


def _expand_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} and $VAR_NAME patterns with env values."""
    import re
    def _replace(match):
        var_name = match.group(1) or match.group(2)
        return os.environ.get(var_name, match.group(0))
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', _replace, text)


def load_soul(soul_path: Path = None) -> str:
    """Load and return the SOUL.md coach persona content."""
    if soul_path is None:
        soul_path = PROFILE_DIR / "SOUL.md"
    return soul_path.read_text()


def get_port(config: dict = None) -> int:
    """Get the configured service port."""
    if config is None:
        config = load_profile_config()
    return int(config.get("port", 8642))


# Last-resort model when the profile has none. gemini-2.5-flash, the previous
# fallback, is retired by Google on 2026-10-16.
DEFAULT_MODEL = "google/gemini-3.8-flash"

# Routing tiers a profile may define. ``utility`` is for the coach's own
# housekeeping calls (best-of-N judge, memory writer, playbook distiller) —
# never for a student-facing answer. ``fallback`` is the model a turn switches
# to when the routed model's provider fails (429 / 5xx / retries exhausted).
# ``quick`` is the model for the one-sentence first reaction of a two-stage
# answer (see COACH_TWO_STAGE); unset → the fast tier.
MODEL_TIERS = ("fast", "analysis", "deep", "utility", "fallback", "quick")


def fallback_model_for(routed_model: str, config: dict = None) -> Optional[str]:
    """Model to switch to when ``routed_model``'s provider fails this turn.

    The ``fallback`` tier, unless the turn is already on it (a game review on
    Gemini falls back to the fast model instead). ``None`` when nothing else is
    configured — the framework then fails the turn as before.
    """
    tiers = get_model_config(config).get("tiers", {}) or {}
    for candidate in (tiers.get("fallback"), tiers.get("fast")):
        if candidate and candidate != routed_model:
            return candidate
    return None


def quick_model(config: dict = None) -> str:
    """Model for the first-stage reaction: the ``quick`` tier, else ``fast``."""
    mc = get_model_config(config)
    tiers = mc.get("tiers", {}) or {}
    return tiers.get("quick") or tiers.get("fast") or mc.get("default") or DEFAULT_MODEL


def get_model_config(config: dict = None) -> dict:
    """Get model routing configuration.

    Environment overrides let production switch or roll back a model without
    a deploy: ``COACH_MODEL_DEFAULT`` and ``COACH_MODEL_<TIER>`` (e.g.
    ``COACH_MODEL_FAST=openai/gpt-5.6-luna``).
    """
    if config is None:
        config = load_profile_config()
    tiers = dict(config.get("model_tiers", {}) or {})
    for tier in MODEL_TIERS:
        override = os.environ.get(f"COACH_MODEL_{tier.upper()}")
        if override:
            tiers[tier] = override
    default = (
        os.environ.get("COACH_MODEL_DEFAULT")
        or config.get("model", {}).get("default")
        or tiers.get("fast")
        or DEFAULT_MODEL
    )
    return {
        "default": default,
        "provider": config.get("model", {}).get("provider", "openrouter"),
        "tiers": tiers,
    }


def utility_model(config: dict = None) -> str:
    """Model for the coach's housekeeping LLM calls (judge, memory, playbook)."""
    mc = get_model_config(config)
    tiers = mc.get("tiers", {}) or {}
    return tiers.get("utility") or tiers.get("fast") or mc.get("default") or DEFAULT_MODEL


def get_api_key() -> str:
    """Get the HERMES_API_KEY for request authentication."""
    return os.environ.get("HERMES_API_KEY", "")


# Mastra CCP (chess-coach-protocol) analysis service. Hermes calls this HTTP
# endpoint to reuse Mastra's PositionPrompter for board analysis, falling back
# to the local Python port on any failure.
MASTRA_CCP_URL = os.environ.get(
    "MASTRA_CCP_URL", "http://localhost:3000/api/position-analysis"
)
# Short timeout (seconds) so a slow/unreachable Mastra never blocks a coach turn.
MASTRA_CCP_TIMEOUT = float(os.environ.get("MASTRA_CCP_TIMEOUT", "2.0"))


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean environment flag (1/true/yes/on -> True)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Coach input hygiene: NFKC-normalize inbound free-text user messages and strip
# zero-width/control chars (mirrors Mastra's UnicodeNormalizer). Default OFF so
# production behavior is byte-identical; enable with COACH_NORMALIZE_INPUT=true.
COACH_NORMALIZE_INPUT = _env_flag("COACH_NORMALIZE_INPUT", False)

# Semantic tool subsetting: select a query-relevant topK subset of chess tools
# per turn instead of sending all ~20 schemas. Default ON to shrink the per-turn
# token payload and cache-align the tool block; the always-present core set keeps
# board/engine tools available every turn. Disable without a deploy with
# COACH_TOOL_SUBSET=false. The topK (excluding the core set) is configurable.
COACH_TOOL_SUBSET = _env_flag("COACH_TOOL_SUBSET", True)

# Emit a {"usage": …} SSE frame per text turn (model bench / diagnostics). Off in prod.
COACH_EMIT_USAGE = _env_flag("COACH_EMIT_USAGE", False)

# Reasoning effort sent to reasoning-capable models via OpenRouter (DeepSeek, Claude,
# OpenAI, Gemini 2.x). The framework defaults to "medium"; on DeepSeek that meant
# 60–105 s of hidden thinking before the first word on some turns (bench 2026-09-23).
# "low" keeps the tool discipline and cuts the wait. Empty string = framework default;
# "none" switches the hidden thinking off — the default since 2026-09-28: with the
# engine line in the turn the model no longer has to work out moves itself, and
# on the bench DeepSeek without thinking (fastest providers, prewarmed position)
# started answering at 0.9 s p50 / 4.7 s p90 against 5.4 / 24.8 s with "low", with
# the engine grader's correctness 0.61 against 0.55 for production before.
# COACH_REASONING_EFFORT=low brings the thinking back.
COACH_REASONING_EFFORT = os.environ.get("COACH_REASONING_EFFORT", "none").strip()
# Thinking level for Gemini 3 models (the deep tier: game reviews, the fallback).
# The framework forwards reasoning settings only to "google/gemini-2*", so Gemini
# 3.8 Flash thought at its default on every step of a review — ~8 s per call
# against ~3 s at "minimal" (2026-09-28, OpenRouter). Gemini 3 cannot switch
# thinking off ("Reasoning is mandatory", HTTP 400), so "none" means "minimal".
# Empty string = the provider's default.
COACH_GEMINI_REASONING_EFFORT = os.environ.get("COACH_GEMINI_REASONING_EFFORT", "minimal").strip()
# OpenRouter provider order for the coach's calls: "throughput" / "latency" / "price";
# empty = OpenRouter's default, which leans to the cheapest providers. For DeepSeek
# V4.1 Flash those run several times slower and some serve an fp4-compressed
# model: the same answer started at 3.5-7.2 s by default and 2.4-3.2 s with
# "throughput" (Together), and 36 bench turns still cost $0.13-0.19 by the balance.
COACH_PROVIDER_SORT = os.environ.get("COACH_PROVIDER_SORT", "throughput").strip()
COACH_TOOL_SUBSET_TOPK = int(os.environ.get("COACH_TOOL_SUBSET_TOPK", "7"))

# Answer length. "brief" (default since 2026-09-28) adds a length rule to the
# prompt: the verdict first, a few sentences, depth on request — answers 3x
# shorter and the whole turn 3.1 s p50 against 5.2 s on the bench. "full" leaves
# it to the persona (SOUL.md): answers of 400–1300 tokens with headings and
# lists. COACH_ANSWER_STYLE=full brings the long answers back without a deploy.
COACH_ANSWER_STYLE = os.environ.get("COACH_ANSWER_STYLE", "brief").strip().lower()
# A direct question («есть мат в два?», «это выигрыш?», «какой первый ход?») gets the
# answer first, a guiding question only after it (voice bench, 2026-10-06: «Да, ты
# прав! Видишь какой-нибудь шах?» instead of the mate). 0 = the Socratic persona as before.
COACH_DIRECT_ANSWERS = os.environ.get("COACH_DIRECT_ANSWERS", "1").strip().lower() not in ("0", "false", "no", "off")

# A provider that goes silent mid-answer: the framework waited 120 s for the next
# byte (HERMES_STREAM_READ_TIMEOUT) and 180 s for the next chunk
# (HERMES_STREAM_STALE_TIMEOUT) — on the bench of 2026-09-28 one answer stopped
# mid-word at 2.3 s and the turn closed at 125 s. The coach's models send their
# first chunk within seconds (no hidden thinking), so a silence of this many
# seconds is a dead connection: before any text the framework retries it, after
# some text the turn ends with a note to the student (server._watch_stream_cuts).
# The framework's own env vars, when set, win.
COACH_STREAM_STALL_S = float(os.environ.get("COACH_STREAM_STALL_S", "30"))
os.environ.setdefault("HERMES_STREAM_READ_TIMEOUT", str(COACH_STREAM_STALL_S))
os.environ.setdefault("HERMES_STREAM_STALE_TIMEOUT", str(2 * COACH_STREAM_STALL_S))

# Two-stage answer (decision with the customer 2026-09-23): the student hears a
# one-sentence reaction within ~1–1.5 s while the full engine-checked answer is
# still being computed (its first token arrives only after every tool call,
# p50 15–23 s on the bench). The reaction is a separate, tool-free model call
# streamed first; the answer follows after a blank line in the same message.
# It never gives a move or an evaluation — that is the second stage's job.
#   COACH_TWO_STAGE          — kill switch (default ON).
#   COACH_QUICK_BUDGET_MS    — the reaction is abandoned if it has not started
#                              streaming within this budget or the full answer
#                              arrives first (default 2500 ms).
#   COACH_QUICK_MAX_TOKENS   — hard cap on the reaction length.
#   COACH_MODEL_QUICK        — model for the reaction (default: the fast tier).
COACH_TWO_STAGE = _env_flag("COACH_TWO_STAGE", True)
COACH_QUICK_BUDGET_MS = int(os.environ.get("COACH_QUICK_BUDGET_MS", "2500"))
COACH_QUICK_MAX_TOKENS = int(os.environ.get("COACH_QUICK_MAX_TOKENS", "60"))

# Engine line in the text turn (2026-09-27): when the request carries the board,
# Stockfish starts the moment the question arrives — alongside the profile load,
# the prompt build and the reaction — and its top moves go into the turn context,
# so "what should I play here?" is answered without an analyze_position round
# trip (bench 2026-09-27: the model's first call plus the engine took 7–20 s
# before the answer's first word).
#   COACH_ENGINE_NOTE              — kill switch (default ON).
#   COACH_ENGINE_NOTE_WAIT_MS      — how long the agent waits for the analysis
#                                    before it starts without it (default 2500 ms).
#   COACH_ENGINE_NOTE_MOVETIME_MS  — the engine searches this long rather than to
#                                    a fixed depth, so the line is ready within the
#                                    wait whatever the host's CPU (default 1500 ms;
#                                    at depth 16 it missed the wait in 16 of 25
#                                    turns on the bench).
COACH_ENGINE_NOTE = _env_flag("COACH_ENGINE_NOTE", True)
COACH_ENGINE_NOTE_WAIT_MS = int(os.environ.get("COACH_ENGINE_NOTE_WAIT_MS", "2500"))
COACH_ENGINE_NOTE_MOVETIME_MS = int(os.environ.get("COACH_ENGINE_NOTE_MOVETIME_MS", "1500"))

# Game review pre-step (2026-09-29): a message with a game in it gets the game
# loaded on the board and its critical moments found by the server the moment it
# arrives, beside the reaction; the model then writes the review in one step.
#   COACH_REVIEW_PRESTEP  — kill switch (default ON).
#   COACH_REVIEW_WAIT_MS  — how long the turn waits for the scan (default 6000 ms;
#                           a 25-move game takes 1-2 s at depth 12).
COACH_REVIEW_PRESTEP = _env_flag("COACH_REVIEW_PRESTEP", True)
COACH_REVIEW_WAIT_MS = int(os.environ.get("COACH_REVIEW_WAIT_MS", "6000"))

# Threads of the event loop's default executor (2026-09-30): every turn holds
# one for the agent call and one for the reaction; the default (cpu+4) queued
# the next students' session/profile steps invisibly.
COACH_EXECUTOR_THREADS = int(os.environ.get("COACH_EXECUTOR_THREADS", "32"))

# Opening pre-step (2026-09-30): a message that names an opening («как играть
# против жареной печени») gets the ECO-book line on the board and in the turn —
# the line, the book's alternatives (the defences) and facts of its final
# position — before the model is called (src/opening_knowledge.py).
#   COACH_OPENING_PRESTEP — kill switch (default ON).
COACH_OPENING_PRESTEP = _env_flag("COACH_OPENING_PRESTEP", True)

# Answer check (2026-09-30): each finished sentence of a text answer is checked
# on the board before it is shown (src/answer_check.py) — a piece moving or
# attacking against its pattern, a move no piece can make, moves given for the
# wrong opening. A wrong sentence is not shown; the rest of the answer is
# rewritten from there by one tool-free call told what was wrong.
#   COACH_ANSWER_CHECK      — kill switch (default ON): off streams as before.
#   COACH_ANSWER_FIX        — rewrite after a wrong sentence (default ON); off
#                             drops the wrong sentences only.
#   COACH_ANSWER_FIX_MAX_TOKENS / COACH_ANSWER_FIX_TIMEOUT_S — the rewrite call.
COACH_ANSWER_CHECK = _env_flag("COACH_ANSWER_CHECK", True)
COACH_ANSWER_FIX = _env_flag("COACH_ANSWER_FIX", True)
COACH_ANSWER_FIX_MAX_TOKENS = int(os.environ.get("COACH_ANSWER_FIX_MAX_TOKENS", "400"))
COACH_ANSWER_FIX_TIMEOUT_S = float(os.environ.get("COACH_ANSWER_FIX_TIMEOUT_S", "12"))

# The student's idea on the board (2026-10-04): a move named in the message
# («а если Rg1?», «поставить ладью на g1») is played on the board the moment it
# arrives and Stockfish looks at the position after it; the facts go into the
# turn context before the model writes. The coach's own recommendation
# («сыграй Rg1») is checked by the engine before the sentence is shown — a move
# that gives away COACH_MOVE_VERIFY_CP centipawns or more is rewritten like a
# wrong claim. Both are the fix for the client's hallucinations in hypothetical
# lines (2026-10-01): the model reasoned about positions nobody had looked at.
#   COACH_HYPOTHETICAL_NOTE         — kill switch (default ON).
#   COACH_HYPOTHETICAL_MOVETIME_MS  — the engine's time per position (default 300 ms;
#                                     up to 3 moves, one thread, beside the engine line).
#   COACH_MOVE_VERIFY               — kill switch for the recommendation check (default ON).
#   COACH_MOVE_VERIFY_MOVETIME_MS   — its engine time (default 300 ms; the current
#                                     position usually comes from the engine line's cache).
#   COACH_MOVE_VERIFY_CP            — the loss that makes a recommendation wrong (default 150).
#   COACH_MOVE_VERIFY_PER_TURN      — recommendations checked per answer (default 2).
COACH_HYPOTHETICAL_NOTE = _env_flag("COACH_HYPOTHETICAL_NOTE", True)
COACH_HYPOTHETICAL_MOVETIME_MS = int(os.environ.get("COACH_HYPOTHETICAL_MOVETIME_MS", "300"))
# The voice twin (/api/coach/voice/idea): the [Idea] line came 0.3–0.8 s after the
# voice coach had started answering (voice bench, 2026-10-06), so it searches shorter.
COACH_VOICE_IDEA_MOVETIME_MS = int(os.environ.get("COACH_VOICE_IDEA_MOVETIME_MS", "150"))
COACH_MOVE_VERIFY = _env_flag("COACH_MOVE_VERIFY", True)
COACH_MOVE_VERIFY_MOVETIME_MS = int(os.environ.get("COACH_MOVE_VERIFY_MOVETIME_MS", "300"))
COACH_MOVE_VERIFY_CP = int(os.environ.get("COACH_MOVE_VERIFY_CP", "150"))
COACH_MOVE_VERIFY_PER_TURN = int(os.environ.get("COACH_MOVE_VERIFY_PER_TURN", "4"))
# «Дай задачу на связку» (2026-10-05): the task comes from the site's own sets on
# the theme first (the student's programme, with the set's address), the Lichess
# puzzle set only when the site has none. COACH_PUZZLES_FROM_SITE=0 → Lichess as before.
COACH_PUZZLES_FROM_SITE = _env_flag("COACH_PUZZLES_FROM_SITE", True)

# Load the framework, the engines and the ECO book when the server starts, not
# on the first students' questions (1-2 s slower after every restart).
COACH_WARMUP = _env_flag("COACH_WARMUP", True)

# Provider fallback: when the routed model's provider answers 429/402 or keeps
# failing, the turn switches to the ``fallback`` tier (config.yaml) instead of
# handing the student the error text (bench 2026-09-23: 19 of 36 Gemini turns
# came back as "API call failed after 3 retries: HTTP 429 …" in the chat).
# Disable with COACH_MODEL_FALLBACK_ENABLED=0 to fail the turn as before.
COACH_MODEL_FALLBACK_ENABLED = _env_flag("COACH_MODEL_FALLBACK_ENABLED", True)

# Per-student memory writer (CL Phase 1): after each completed text-chat turn,
# a cheap off-request-path LLM call reflects on the turn and accumulates durable
# student facts (weaknesses/goals/style) into user_profiles, plus a Reflexion-
# lite failure-memory row when the engine refutes a coach move. Default OFF so
# behavior is byte-identical to today; enable with COACH_MEMORY_WRITER=1.
COACH_MEMORY_WRITER = _env_flag("COACH_MEMORY_WRITER", False)

# Game retrieval digest (CL Phase 1, Slice 2): inject a compact "Recent games"
# block into the system prompt from the student's own reviewed games
# (coach_game_insights). Context injection only — never writes anywhere. Default
# OFF so behavior is byte-identical to today; enable with COACH_GAME_RAG=1.
COACH_GAME_RAG = _env_flag("COACH_GAME_RAG", False)

# Coaching playbook (CL Phase 2, Slice 1): inject a compact "Coaching playbook
# (engine-verified)" block into the system prompt from an evolving store of
# distilled, engine-verified coaching patterns (coach_playbook). Context
# injection only on the turn path — the Generator/Reflector/Curator curation
# loop runs OFFLINE via scripts/build_playbook.py, never inline in a chat turn.
# Default OFF so behavior is byte-identical to today; enable with COACH_PLAYBOOK=1.
COACH_PLAYBOOK = _env_flag("COACH_PLAYBOOK", False)

# Automatic curriculum (CL Phase 2, Slice 2): inject a compact "Training focus
# (engine-measured)" block into the system prompt from a per-student curriculum
# (coach_curriculum) keyed on engine-measured learnability — the themes where the
# engine says the student blunders most, at a difficulty near their ~50% solve-
# rate frontier. Context injection only on the turn path — the curriculum is
# computed OFFLINE via scripts/build_curriculum.py (deterministic aggregation, no
# LLM calls), never inline in a chat turn. Default OFF so behavior is byte-
# identical to today; enable with COACH_CURRICULUM=1.
COACH_CURRICULUM = _env_flag("COACH_CURRICULUM", False)

# Best-of-N with engine selection (CL Phase 2, Slice 3): for a position-anchored
# coach turn, generate several candidate explanations, let the ENGINE rank the
# correctness channel (via engine_grounded), then a cheap-tier LLM judge picks
# the clearest among the engine-PASSING candidates only. The engine gatekeeps
# correctness; the judge can never promote an engine-failing candidate. Applies
# only to analysis turns with a known FEN; the winner is streamed through the
# existing SSE machinery so the client contract is unchanged. Default OFF so
# behavior is byte-identical to today (same single agent.chat call, same
# streaming, zero extra model/engine calls); enable with COACH_BESTOFN=1.
#   COACH_BESTOFN_N         — candidates to generate (default 2, hard max 4).
#   COACH_BESTOFN_BUDGET_MS — wall-clock budget for the whole pipeline (default
#                             4500ms; candidates generate concurrently so this
#                             fits under 5s); on overrun the best-scored-so-far
#                             (or first candidate) is returned so the user always
#                             gets a reply.
COACH_BESTOFN = _env_flag("COACH_BESTOFN", False)
COACH_BESTOFN_N = int(os.environ.get("COACH_BESTOFN_N", "2"))
COACH_BESTOFN_BUDGET_MS = int(os.environ.get("COACH_BESTOFN_BUDGET_MS", "4500"))

# Self-hosted engine MCP: connect to external MCP servers configured in
# ~/.hermes/config.yaml (mcp_servers) at startup and expose their tools to the
# coach under `mcp-*` toolsets. Default OFF so the coach runs on native
# in-process tools only and behavior is byte-identical; enable with
# COACH_MCP_ENABLED=true (and configure mcp_servers). See engine-mcp/.
COACH_MCP_ENABLED = _env_flag("COACH_MCP_ENABLED", False)
