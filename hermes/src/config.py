"""Configuration loader for Hermes Chess Coach."""

import functools
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

# The site's lesson a topic/lesson tool found, added as the last line when the
# model left its link out (production sweep 2026-10-07: 32 of 48 topics had it).
COACH_LESSON_LINK = os.environ.get("COACH_LESSON_LINK", "1").strip().lower() not in ("0", "false", "no", "off")

# The tutor on the lesson pages gets what the coach gets before it answers (2026-10-08): the engine
# line of the student's board (or its facts), the moves the message names played by the engine, and
# its own recommended move checked by the engine. 0 — the book and the answer check only, as before.
COACH_LESSON_FACTS = os.environ.get("COACH_LESSON_FACTS", "1").strip().lower() not in ("0", "false", "no", "off")

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
# The hidden board for theory questions (src/question_position.py, 2026-10-20): the position a
# question is about — an opening line's end, a textbook endgame by material, a topic's example — is
# analysed on a second board the student does not see; their own position stays. Kill switch and
# the engine's time per hidden position.
COACH_HIDDEN_BOARD = _env_flag("COACH_HIDDEN_BOARD", True)
# The model goes online for a question about the present («кто сейчас чемпион мира?»): OpenRouter's web
# plugin by the model-id suffix (src/current_facts.web_model; Asan's choice, 20.10 — about $0.02 a turn,
# only on such turns). Kill switch and the suffix.
COACH_WEB_ONLINE = _env_flag("COACH_WEB_ONLINE", True)
COACH_WEB_ONLINE_SUFFIX = os.environ.get("COACH_WEB_ONLINE_SUFFIX", ":online")
COACH_HIDDEN_BOARD_MOVETIME_MS = int(os.environ.get("COACH_HIDDEN_BOARD_MOVETIME_MS", "400"))
# A game asked for in words, or the student's move written on its own during a game: the server
# starts the game / plays the move before the model answers (src/game_intent.py, 2026-10-12).
COACH_GAME_PRESTEP = _env_flag("COACH_GAME_PRESTEP", True)
# A puzzle asked for in words («дай задачу на связку», «ещё задачу», «дай три задачи», «дальше») is put on
# the board by the server before the model answers (src/server._puzzle_prestep, 21.10): left to the model,
# «Ещё задачу» on production kept hinting at the old task without calling get_puzzle at all.
COACH_PUZZLE_PRESTEP = _env_flag("COACH_PUZZLE_PRESTEP", True)
# The position on the board recognised (2026-10-22): a task of the site's lessons found by its position
# gets its lesson and solution in the turn (src/site_puzzle_lookup — the programme run's 14 misses were
# tasks that came as a FEN, not through get_lesson); a position on a known opening trap's line gets the
# trap's lines (src/trap_positions — «да, можно взять e5» in the Blackburne Shilling position, prod 19.10).
COACH_SITE_PUZZLE_LOOKUP = _env_flag("COACH_SITE_PUZZLE_LOOKUP", True)
COACH_TRAP_POSITIONS = _env_flag("COACH_TRAP_POSITIONS", True)

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
# The relation checker in the answer check (src/answer_check_relations.py, plan 30.10): who attacks, defends,
# pins, holds what, judged on the board each claim is about.
#   COACH_RELATION_CHECK — off | shadow | on (default on). shadow computes and logs the issues but never cuts a
#                          sentence; on cuts it and sends the issue to the rewrite. Read at call time, so a test
#                          or the harness (scripts/eval_relations.py) can patch it.
COACH_RELATION_CHECK = os.environ.get("COACH_RELATION_CHECK", "on").strip().lower()
# The games-database checks of the answer check (src/answer_check_db.py, 03–04.11), each off | shadow | on, default
# shadow: computed and logged (the turn's db_check event), never cut — the last check of 04.11 still cut true sentences.
#   COACH_DB_CLAIM_CHECK    — «поиск ничего не нашёл», «нет доступа к базе» with no empty database search of the turn.
#   COACH_LOADED_GAME_CHECK — a move of the database game on the board told wrong («на 13-м ходу белые взяли…»).
# Read at call time (src/answer_check_db.mode).
COACH_DB_CLAIM_CHECK = os.environ.get("COACH_DB_CLAIM_CHECK", "shadow").strip().lower()
COACH_LOADED_GAME_CHECK = os.environ.get("COACH_LOADED_GAME_CHECK", "shadow").strip().lower()
# The proof of the rewrite (src/rewrite_proof.py, fix1102 K6): a rewrite's sentence with a board word is shown only
# when the check proved it. off | shadow | on, default shadow: the live run of 04.11 (175 inputs) dropped 36 of 40
# rewrites as unproven, at least 15 of them true («Black» the only issue, the Russian rewrite right) — shadow logs
# what the proof would drop (answer_check event, unproven_shadow) and shows the rewrite as production does.
# Read at call time.
COACH_REWRITE_PROOF = os.environ.get("COACH_REWRITE_PROOF", "shadow").strip().lower()
# The student's side decided once by the server (src/student_side.py, 06.11). off | shadow | on, default shadow.
# shadow is pure logging: the decision is written to the student_side event every turn (with what ``on`` would apply),
# while the answer check's colour, the rewrite's side note, the model's prompt and the voice check stay exactly prod
# 04.11's (a game; a move of the question «already played» is the student's — 2026-10-08). ``on`` applies it: «Они
# сыграли f5» keeps the student White (t25), «Белые поставили коня на d5» drops the pin (t46), «я играю чёрными» is
# told to the model, a master game on the board is nobody's; where nothing is told about the move («Qxf7 — это мат?»)
# the 04.11 pin stays. ``off`` behaves as shadow. Read at call time (src/student_side.mode).
COACH_STUDENT_SIDE = os.environ.get("COACH_STUDENT_SIDE", "shadow").strip().lower()

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
# A line the coach writes with its outcome («…Qxd5+, и ты забираешь ферзя», «опасная для чёрных игра», «на четыре
# пешки хуже») is judged by the engine at the line's end in the same stage and budget as a recommendation
# (src/line_verdict.py; prod check 29.10).
#   COACH_LINE_VERDICT — kill switch (default ON; off with COACH_MOVE_VERIFY too).
COACH_LINE_VERDICT = _env_flag("COACH_LINE_VERDICT", True)
# «после Kd5 a6 Kc6 — ничья» (30.10): an outcome claim at the end of a written line in an ending of ≤ 7 pieces is
# judged by the tablebase on the line's last position (src/endgame_claims.py) — at most this many lookups per
# answer (each ≤ COACH_TABLEBASE_TIMEOUT_S, cached); 0 turns the line lookups off.
COACH_TABLEBASE_LINE_CHECKS = int(os.environ.get("COACH_TABLEBASE_LINE_CHECKS", "3"))
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

# ── Detectors of plan 31.10 (detect-1031; next1031/PLAN.md §1.3, §7) ────────────────────────────────────────────
# Each new answer-check mechanism has a name and its own switch, read at call time (tests and the replay patch the
# environment or these names), so one detector rolls back alone without a deploy:
#   COACH_DETECTORS_OFF    — comma list of detector names that do nothing;
#   COACH_DETECTORS_SHADOW — comma list of detector names that compute and log their issue but never cut.
# OFF wins over SHADOW, SHADOW over the default below. The relation detectors (RELATION_DETECTORS) also obey
# COACH_RELATION_CHECK: off there turns them off, shadow there caps them at shadow. Whatever the switches say, the
# /learn lesson tutor gets none of them (the team's feature, Асан 19.10); on a game move comment the relation detectors
# are at most shadow, the others run as in a chat answer.
DETECTOR_DEFAULTS = {
    # WP-0's "book_wait" is no detector (verify1102 B3): nothing in Hermes waits for the book index — the replay warms it
    # as production's warm-up does (src/server._warm_up, as on main), so a switch for it would switch nothing.
    # P1 game record
    "recap_scope": "on", "material_order": "on", "student_capture": "on", "gave_up": "on", "block_kind": "on",
    "free_capture": "on", "propose_vocab": "on", "plan_place": "on", "start_scene": "on",
    # P2 openings
    "open_plain": "on", "open_recap": "on", "open_character": "shadow", "open_defining": "shadow",
    # P3A grammar, P3B scene + judge, P3D board rules
    "pin_escape": "on", "pin_noun": "shadow", "locked": "on", "cover_cause": "on",
    "idea_scope": "on", "start_cue": "on", "bare_pawn_line": "shadow", "loaded_line": "shadow",
    # fix1101 F2: «<piece> стоит на <square>» on the board now, read by the scene (src/claim_scene._placement_claims);
    # on since 02.11: 0 false records on the 1,021 true sentences of review-fp and review-fp2, 0 new corpus flags, 0 of
    # the held-out true controls (review-miss2 place_now 1/16 in shadow, 15/16 on)
    "placement": "on",
    "retreat_cover": "on", "prevents": "on", "checks_geometry": "on", "only_move_orders": "on",
    # P4 engine claims (trade_swing_named also needs COACH_TRADE_SWING_NAMED)
    "piece_decides": "on", "trade_swing_named": "off",
    # P5 endgames
    "race_distance": "on", "mate_squares": "on", "king_direction": "shadow",
    # P6 records
    "trades": "on",
    # stage-3 integration (src/hypothetical._ending_unproven): a ≤7-piece ending the tablebase does not answer, won
    # before and after the move by the engine, is left unjudged by the recommended-move check (fix1101 F8)
    "ending_unproven": "on",
    # stage-2 integration (src/hypothetical._tablebase_keeps): a move the tablebase says keeps the result is no mistake,
    # whatever the engine's number drops by; its own switch since review-wiring2 01.11 (off = main's engine rule)
    "tablebase_keeps": "on",
    # a game move comment's context carries the game's record (fix 01.11 F7); off = main's comment context
    "comment_record": "on",
    # F5's structure readings (verify1102 B3), which the lesson tutor never had: proposals (_PROPOSES' new words
    # «играем», «выбери», the stop at «3...Nf6» dots, «не давая …», «Kd2?», «…, но только после f4»), a recapture pair
    # judged where its line stands, a written line's quoted move and next ply; off = main's readings
    "structure_read": "on",
    # fix1102 K4: rule talk («Рокировка разрешена, только если …», «Двойной знак означает …») is not judged on the board
    # (src/claim_scope.rule_spans); off = every detector reads the whole sentence, as before
    "rule_scope": "on",
    # voice 02.11: a move proposed in words («пойти ферзём на d1», «пешкой на d3») that has no legal form on the board
    # now — the piece already there, the square taken, the way blocked (src/answer_check._word_move_issues)
    "word_move": "on",
    # voice1102: the reason given for «castling is impossible» judged against the rule (src/castle_reason.py): a square
    # off the king's path («поле f2 под боем»), a square nothing attacks, an attacker that does not attack it, a check
    # that is not there, a piece in the way that is not; off = the possibility alone is judged, as before
    "castle_reason": "on",
    # review 02.11: a written move after a proposal word that has no legal form now («Сыграй Qg4», «Лучше Nd5»)
    "word_move_san": "on",
    # review 02.11: castling proposed or called available when it cannot be played now («Рокируйся коротко», «Давай
    # рокируемся», «Сыграй O-O», «королём на g1»), judged by src/board_rules.castling_status
    "castle_advice": "on",
    # review-miss 03.11: a check claimed for a move told in words or notation («Конём на g4 — шах», «Иди ладьёй на b1 с
    # шахом», «Ход Na5 объявляет шах») or for the board now («Внимание: тебе шах») judged by board.gives_check / is_check
    "check_claim": "on",
    # review-fp 03.11: a standing claim cut on the board now is re-judged on the board after the move told just before
    # it (this sentence's or the sentence before's: «Сыграй Nd5. Конь атакует слона e3»); off = judged on the board now
    "after_told_move": "on",
    # review-miss 03.11: a material claim with no amount («Ты отстаёшь по материалу», «Материал равный», «ты потерял
    # качество») judged by the sign of the balance on the board now
    "material_direction": "on",
    # review-miss 03.11: a named side said to have castled («Ты уже рокировался»), or to still be able to castle / to be
    # able no longer («Соперник ещё может рокироваться», «…уже не может сделать короткую рокировку»), by castling_status
    "castle_state": "on",
}
RELATION_DETECTORS = frozenset({
    "pin_escape", "pin_noun", "locked", "cover_cause", "idea_scope", "start_cue", "bare_pawn_line", "loaded_line",
    "retreat_cover", "prevents", "checks_geometry", "only_move_orders", "placement",
})
# Relation detectors whose judge reads the game's record (the capture on the square), not a board the comment
# describes: on a game move comment they follow the game-record rule, not the relation cap (review-miss2 01.11).
GAME_RECORD_RELATIONS = frozenset({"cover_cause"})
_MODE_RANK = {"off": 0, "shadow": 1, "on": 2}


def _env_names(name: str) -> frozenset:
    return _parse_names(os.environ.get(name) or "")


@functools.lru_cache(maxsize=64)
def _parse_names(raw: str) -> frozenset:
    """The comma list *raw* as lower-case names; cached by the raw string, so a changed variable is read at once
    while the per-sentence switch lookups (every relation sentence asks several) do not re-split it."""
    return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())


def detector_mode(name: str, ctx=None) -> str:
    """'on' | 'shadow' | 'off' for the detector *name* (DETECTOR_DEFAULTS), read now. An unknown name is 'off' — a
    package cannot switch on a detector the plan does not list (tests/unit/test_wp0_1031.py checks the names)."""
    key = (name or "").strip().lower()
    got = DETECTOR_DEFAULTS.get(key)
    if got is None:
        return "off"
    if key in _env_names("COACH_DETECTORS_OFF"):
        return "off"
    if key in _env_names("COACH_DETECTORS_SHADOW"):
        got = "shadow"
    if key == "trade_swing_named":
        on = globals().get("COACH_TRADE_SWING_NAMED", False)
        raw = os.environ.get("COACH_TRADE_SWING_NAMED")
        if raw is not None:
            on = raw.strip().lower() in ("1", "true", "yes", "on")
        got = "on" if on and key not in _env_names("COACH_DETECTORS_SHADOW") else ("shadow" if on else "off")
    if key in RELATION_DETECTORS:
        raw = str(globals().get("COACH_RELATION_CHECK", "on") or "").strip().lower()
        rel = "off" if raw in ("0", "off", "false", "no") else ("on" if raw in ("1", "on", "true", "yes") else "shadow")
        got = min(got, rel, key=_MODE_RANK.get)
    surface = getattr(ctx, "relation_surface", "text") if ctx is not None else "text"
    if surface == "lesson":
        return "off"
    if surface == "game" and key in RELATION_DETECTORS and key not in GAME_RECORD_RELATIONS:
        # A game move comment caps the relation detectors (not reviewed on comments yet); the game-record, opening,
        # engine and endgame detectors judge a comment as they judge a chat answer in the same game (fix 01.11: with
        # every detector capped the comment surface caught 0 of the 8 graded game sentences).
        got = min(got, "shadow", key=_MODE_RANK.get)
    return got


def detector_on(name: str, ctx=None) -> bool:
    """The detector may cut a sentence (mode 'on')."""
    return detector_mode(name, ctx) == "on"


def detector_enabled(name: str, ctx=None) -> bool:
    """The detector runs at all (mode 'on' or 'shadow'); a shadow issue is logged, never shown."""
    return detector_mode(name, ctx) != "off"


# «отдают слона за пешку» (pawn-b3-bare): the swing of a trade the sentence names is judged by that trade's value.
# Off until Асан agrees to change the tolerance he approved (plan 31.10 §7).
COACH_TRADE_SWING_NAMED = _env_flag("COACH_TRADE_SWING_NAMED", False)
# Prevention (P8): the facts of the turn (fork facts vetted by the engine, piece safety, attack balance, the game's
# material and captures, opening ideas, rules from the board) go to the model; off renders nothing new.
COACH_TURN_FACTS = _env_flag("COACH_TURN_FACTS", True)
# Prevention (voice 02.11): the coach's rule facts (voice note, text turn) say castling with the king's squares that
# decide it and the side to move's pawn and queen moves (src/board_rules.rule_facts explicit); off = as before. The
# lesson tutor and the hidden board never ask for them.
COACH_EXPLICIT_RULES = _env_flag("COACH_EXPLICIT_RULES", True)
# Speed (P7, next1031/speed): persistent Stockfish processes instead of one process per search, and the board's
# positions analysed while the student thinks. Each has its own off switch (0 = today's behaviour).
#   STOCKFISH_POOL             — the pool on/off (default on).
#   STOCKFISH_POOL_SIZE        — processes (default min(2, CPUs)), one thread each.
#   STOCKFISH_HASH_MB          — hash per process (default 16, Stockfish's own default and what a process per
#                                search had on main: a depth search from an empty hash then gives the very lines a
#                                new process gives, and trap-legal's depth-17 confirm needs 21 % fewer nodes than at
#                                32 MB — 0.7–0.9 s against 1.04 s, over its 1 s budget; stage-3 integration 31.10).
#   STOCKFISH_RECYCLE_SEARCHES — a process is restarted after this many searches (default 5000).
#   COACH_PRECOMPUTE           — the board-change listener's precompute (default on).
STOCKFISH_POOL = _env_flag("STOCKFISH_POOL", True)
STOCKFISH_POOL_SIZE = max(1, int(os.environ.get("STOCKFISH_POOL_SIZE") or min(2, os.cpu_count() or 1)))
STOCKFISH_HASH_MB = max(1, int(os.environ.get("STOCKFISH_HASH_MB", "16")))
STOCKFISH_RECYCLE_SEARCHES = max(1, int(os.environ.get("STOCKFISH_RECYCLE_SEARCHES", "5000")))
COACH_PRECOMPUTE = _env_flag("COACH_PRECOMPUTE", True)
