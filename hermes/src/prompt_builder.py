"""System prompt builder — combines persona, user profile, and board state.

Assembles the full system prompt for the AI agent from:
1. SOUL.md (chess coach persona)
2. User profile (rating, goals, weaknesses, style)
3. Current board state (FEN, move history if PGN loaded)
4. Available tools summary
5. Platform ratings (auto-synced from linked accounts)
"""

import hashlib
import re
import logging
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from src.user_profile import UserProfile

logger = logging.getLogger(__name__)

# ── Prompt versioning ──────────────────────────────────────────────────
# A stable fingerprint of the coach's system-prompt inputs, stamped onto every
# logged turn and onto coach_messages so a reply can be traced back to the exact
# persona + template that produced it. Bump PROMPT_TEMPLATE_VERSION whenever the
# in-code prompt scaffolding (tool instructions, structure) changes materially;
# SOUL.md edits are picked up automatically via its mtime.
PROMPT_TEMPLATE_VERSION = "17"  # 17: the student's idea is played on the board and judged by the engine before the answer (2026-10-04); 16: the site's lesson comes first and the answer ends with its tasks (2026-10-03); 15: the language the student asks for holds for the session (2026-10-01); 14: an opening named in the message comes with its book line, alternatives and facts (2026-09-30); 13: get_puzzle puts the puzzle on the board itself (2026-09-30); 12: opening names only from the ECO book (2026-09-29); 11: talk about the side to move (2026-09-29); 10: the engine line carries verified facts — threats, hanging and pinned pieces (2026-09-29); 9: the engine block only for questions about the position (2026-09-29); 8: talk like a coach, not an engine report; brief by default (2026-09-28); 2: study-programme tools; 3: knowledge-base tools (2026-09-23); 4: examples only from lessons/base (2026-09-26); 5: engine line in the turn (2026-09-27); 6: arrows as inline marks (2026-09-27); 7: voice — every tool, question-language rule (2026-09-24, merged 2026-09-28)

_prompt_version_lock = threading.Lock()
_prompt_version_cache: Optional[str] = None
_prompt_version_mtime: Optional[float] = None


def _compute_prompt_version(soul_content: str) -> str:
    """First 10 hex chars of sha256(SOUL.md + template version constant)."""
    # The length rule changes the prompt without touching SOUL.md or the template.
    style = "brief" if answer_style_layer() else ""
    digest = hashlib.sha256(
        (soul_content + PROMPT_TEMPLATE_VERSION + style).encode("utf-8")
    ).hexdigest()
    return digest[:10]


def get_prompt_version() -> str:
    """Return the current prompt version, recomputing only on SOUL.md change.

    Reads SOUL.md via the config loader and caches the hash keyed on the file's
    mtime, so the sha256 is computed once and only recomputed when the persona
    file (or the in-code template version) changes. Fully defensive: any failure
    reading SOUL.md falls back to hashing just the template version constant so a
    caller always gets a stable, non-empty version string.
    """
    global _prompt_version_cache, _prompt_version_mtime
    try:
        from src.config import PROFILE_DIR

        soul_path = PROFILE_DIR / "SOUL.md"
        mtime = soul_path.stat().st_mtime
        with _prompt_version_lock:
            if _prompt_version_cache is not None and _prompt_version_mtime == mtime:
                return _prompt_version_cache
            version = _compute_prompt_version(soul_path.read_text())
            _prompt_version_cache = version
            _prompt_version_mtime = mtime
            return version
    except Exception:
        logger.debug("prompt version computation failed; using template-only hash", exc_info=True)
        return _compute_prompt_version("")

# Bounded LRU cache for FEN-keyed board analysis. The analysis block is a pure
# function of the FEN, so an unchanged position can reuse the previous result
# and skip the Mastra CCP HTTP call / local recompute. Only successful results
# are cached — a None/failed lookup is never stored, so a transient failure is
# retried on the next turn (preserving the existing defensive fallback).
_ANALYSIS_CACHE_MAX = 512
_analysis_cache: "OrderedDict[str, str]" = OrderedDict()
_analysis_cache_lock = threading.Lock()


def clear_analysis_cache() -> None:
    """Empty the FEN-keyed board-analysis cache (used by tests)."""
    with _analysis_cache_lock:
        _analysis_cache.clear()


def _resolve_board_analysis(fen: str) -> Optional[str]:
    """Return the board-analysis block for a FEN, with a bounded LRU cache.

    Prefers Mastra's CCP service and falls back to the local Python port on any
    failure — identical to the original inline logic. Successful results are
    cached keyed on the exact FEN string so a repeated position returns the same
    block without a second fetch/recompute. Failed lookups are never cached.
    """
    with _analysis_cache_lock:
        cached = _analysis_cache.get(fen)
        if cached is not None:
            _analysis_cache.move_to_end(fen)
            return cached

    analysis = _fetch_ccp_analysis(fen)
    if not analysis:
        from src.tools.tactical_board import build_board_analysis
        analysis = build_board_analysis(fen)

    if analysis:
        with _analysis_cache_lock:
            _analysis_cache[fen] = analysis
            _analysis_cache.move_to_end(fen)
            while len(_analysis_cache) > _ANALYSIS_CACHE_MAX:
                _analysis_cache.popitem(last=False)
    return analysis


# The fetch runs inside the prompt build, before the reaction can start: a CCP
# service that hangs would add MASTRA_CCP_TIMEOUT to every turn with a board.
# After a timeout the local port is used alone for a while.
_CCP_TIMEOUT_BACKOFF_S = 600.0
_ccp_skip_until = 0.0


def _fetch_ccp_analysis(fen: str) -> Optional[str]:
    """Fetch board analysis from the Mastra CCP HTTP service.

    POSTs {fen} to MASTRA_CCP_URL and returns the `<detailed_board_analysis>`
    block generated by Mastra's PositionPrompter. Fully defensive: returns None
    on any non-200 response, timeout, connection error, or malformed body so the
    caller can fall back to the local Python port.
    """
    global _ccp_skip_until
    if time.monotonic() < _ccp_skip_until:
        return None
    try:
        import httpx

        from src.config import MASTRA_CCP_URL, MASTRA_CCP_TIMEOUT

        if not MASTRA_CCP_URL:
            return None
        try:
            resp = httpx.post(
                MASTRA_CCP_URL, json={"fen": fen}, timeout=MASTRA_CCP_TIMEOUT
            )
        except httpx.TimeoutException:
            _ccp_skip_until = time.monotonic() + _CCP_TIMEOUT_BACKOFF_S
            logger.warning("Mastra CCP timed out; local board analysis only for %.0f s",
                           _CCP_TIMEOUT_BACKOFF_S)
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("valid") and data.get("board_analysis"):
            return data["board_analysis"]
        return None
    except Exception:
        logger.debug("Mastra CCP analysis fetch failed", exc_info=True)
        return None


def _fire_and_forget_sync(user_id: str) -> None:
    """Sync ratings in a background thread. Does not block prompt building."""
    try:
        from src.platform_linking import sync_ratings
        sync_ratings(user_id=user_id)
    except Exception:
        logger.debug("Background rating sync failed for %s", user_id, exc_info=True)


def maybe_sync_ratings(user_id: str) -> None:
    """Trigger a non-blocking background sync of platform ratings."""
    t = threading.Thread(target=_fire_and_forget_sync, args=(user_id,), daemon=True)
    t.start()


LOCALE_TO_LANGUAGE = {
    "ru": "Russian",
    "kz": "Kazakh",
    "kk": "Kazakh",
    "en": "English",
}


def language_rule(locale: str) -> str:
    """The language directive both prompts lead with (text and voice).

    The language of the student's own words wins (TZ 3g); the interface locale
    only decides when a message carries no language of its own. The old rule
    ("respond entirely in <locale>") told the model to use the interface
    language even when the student wrote or spoke in another one.
    """
    interface = LOCALE_TO_LANGUAGE.get(locale, locale)
    return (
        "CRITICAL LANGUAGE RULE: Answer in the language of the student's latest "
        "message — Russian, Kazakh or English — even when it differs from the "
        f"interface language. The interface language is {interface}: use it when "
        'a message shows no language of its own (just a move, a FEN, "ok") and '
        "for the first thing you say. When the student asks you to speak a particular "
        "language — in whatever language they ask — switch to it and stay in it until "
        "they ask otherwise. Never mix languages in one reply and never switch to a "
        "language the student did not use or ask for."
    )


TURN_CONTEXT_HEADER = "[Turn context — supplied by the system, not written by the student]"


def _student_context_blocks(
    user_profile: Optional[UserProfile],
    board_fen: Optional[str] = None,
    move_history: Optional[list[str]] = None,
) -> list[str]:
    """Per-student memory blocks shared by the text and the voice prompt.

    Failure memory, the student's recently reviewed games, the coaching
    playbook and the engine-measured training focus. Each block is flag-gated
    and fail-open, so with every flag off this returns [].
    """
    sections: list[str] = []
    # Failure memory (CL Phase 1): inject the student's most recent verified
    # mistakes so the coach avoids repeating them. Flag-gated (default OFF → this
    # block is a no-op and the prompt is byte-identical) and fully fail-open.
    if user_profile:
        try:
            from src.config import COACH_MEMORY_WRITER

            if COACH_MEMORY_WRITER:
                from src.memory_writer import (
                    load_active_corrections,
                    render_corrections_block,
                )

                block = render_corrections_block(
                    load_active_corrections(user_profile.user_id, limit=3)
                )
                if block:
                    sections.append(block)
        except Exception:
            logger.debug("corrections injection failed", exc_info=True)

    # Game retrieval digest (CL Phase 1, Slice 2): inject a compact summary of the
    # student's own recently reviewed games. Flag-gated (COACH_GAME_RAG, default
    # OFF → no-op, prompt byte-identical) and fully fail-open.
    if user_profile:
        try:
            from src.config import COACH_GAME_RAG

            if COACH_GAME_RAG:
                from src.tools.game_insights import (
                    load_recent_insights,
                    render_games_block,
                )

                block = render_games_block(
                    load_recent_insights(user_profile.user_id, limit=3)
                )
                if block:
                    sections.append(block)
        except Exception:
            logger.debug("game insights injection failed", exc_info=True)

    # Coaching playbook (CL Phase 2, Slice 1): inject up to 3 relevant, engine-
    # verified coaching patterns distilled from real transcripts. Flag-gated
    # (COACH_PLAYBOOK, default OFF → no-op, prompt byte-identical), fully
    # fail-open, and served from an in-process TTL cache so it adds no per-turn
    # DB latency spike. Curation is offline; this only reads.
    try:
        from src.config import COACH_PLAYBOOK

        if COACH_PLAYBOOK:
            from src.playbook import build_turn_context, load_playbook_block

            context = build_turn_context(
                board_fen=board_fen,
                move_history=move_history,
                user_profile=user_profile,
            )
            block = load_playbook_block(context)
            if block:
                sections.append(block)
    except Exception:
        logger.debug("playbook injection failed", exc_info=True)

    # Automatic curriculum (CL Phase 2, Slice 2): inject the student's current
    # "Training focus (engine-measured)" — ≤3 themes keyed on engine-measured
    # learnability (high blunder rate near their ~50% solve frontier). Flag-gated
    # (COACH_CURRICULUM, default OFF → no-op, prompt byte-identical), fully fail-
    # open, and served from an in-process per-user TTL cache so it adds no per-
    # turn DB latency spike. The curriculum is computed OFFLINE; this only reads.
    if user_profile:
        try:
            from src.config import COACH_CURRICULUM

            if COACH_CURRICULUM:
                from src.curriculum import load_curriculum_block

                block = load_curriculum_block(user_profile.user_id)
                if block:
                    sections.append(block)
        except Exception:
            logger.debug("curriculum injection failed", exc_info=True)

    return sections


def build_system_prompt(
    soul_content: str,
    user_profile: Optional[UserProfile] = None,
    board_fen: Optional[str] = None,
    move_history: Optional[list[str]] = None,
    locale: Optional[str] = None,
    return_parts: bool = False,
):
    """Build the full system prompt for the chess coaching agent.

    Args:
        soul_content: The SOUL.md persona text.
        user_profile: Optional user profile for personalization.
        board_fen: Optional current board FEN position.
        move_history: Optional list of SAN moves played so far.
        locale: Optional UI locale code (e.g. 'ru', 'kz', 'en').
        return_parts: When True, return ``(static_prompt, turn_context)``
            instead of one string. The static part (language rule, persona,
            tool guidance) is identical from turn to turn and can be served
            from the provider's prompt cache; the turn context (date, profile,
            memory, board state) changes every turn and belongs in the user
            message, where it cannot bust the cached prefix.

    Returns:
        Complete system prompt string, or a ``(static, turn_context)`` tuple.
    """
    sections = []

    # Inject mandatory language directive before everything else
    if locale:
        sections.append(language_rule(locale))

    # ── Static prefix ──────────────────────────────────────────────────
    # SOUL persona and the tool-usage instructions never change turn-to-turn,
    # so they lead the prompt to form a stable Anthropic prompt-cache prefix.
    # All volatile blocks (current date, profile, board state) come AFTER so a
    # cache hit survives across turns. Order is valid for every provider.
    sections.append(soul_content.rstrip())

    # Tool instructions (static)
    sections.append(
        "## Tool Usage (MANDATORY)\n"
        "You have access to chess tools. You MUST use them — never answer "
        "game/player/opening questions from memory alone.\n\n"
        "### search_master_games\n"
        "ALWAYS call this tool when the user asks about a player's games, "
        "recent tournaments, head-to-head records, or specific game examples. "
        "Never say 'I don't have data' or 'the tournament hasn't happened yet' "
        "without searching first.\n\n"
        "Search tips:\n"
        "- Use the player's SURNAME only (e.g. player=\"Sindarov\" not \"Javohir Sindarov\")\n"
        "- For events, use the key word (e.g. event=\"Candidates\" not \"Candidates Match\")\n"
        "- Always set year_min for recent tournaments (e.g. year_min=2026)\n"
        "- If first search returns no results, retry with broader terms "
        "(drop event filter, widen year range)\n\n"
        "### Board Control — board_control (USE PROACTIVELY)\n"
        "Your PRIMARY teaching tool. The student has an interactive board — use it constantly.\n\n"
        "Actions and when to use them:\n"
        "- **set_fen**: Set a position on the board — ONLY a position that came from a tool "
        "result, the student's game or the student's own message. Never type an example "
        "position from memory: examples of a concept (pin, fork, skewer…) come from "
        "get_topic / get_lesson, which put them on the board themselves.\n"
        "- **load_pgn**: Load a full game on the board. Use when referencing master games "
        "so the student can replay the moves.\n"
        "- **set_puzzle**: Present a tactical puzzle. ALWAYS take it from get_puzzle "
        "(theme + the student's rating) — never invent a puzzle position or solution. "
        "get_puzzle puts its first puzzle on the board itself; set_puzzle with a "
        "puzzle_id is only for another puzzle from its list.\n"
        "- **navigate**: Move forward/back through a loaded game.\n"
        "- **flip_board**: Flip the board perspective.\n"
        "- **clear_board**: Reset the board.\n\n"
        "ARROWS AND HIGHLIGHTS GO INSIDE YOUR ANSWER, not through board_control: write "
        "[[arrows: e2e4 green, g1f3 blue]] or [[squares: d5 e5]] right after the sentence "
        "they illustrate — green for good moves, red for threats, blue for alternatives; "
        "squares for outposts, weak squares, targets. They appear on the board as your text "
        "streams and the student never sees the brackets, so every sentence must read complete "
        "without them: never put a mark in place of a move or a word (\"Take on d5 — "
        "[[arrows: e4d5 green]].\" reaches the student as \"Take on d5 —.\"). "
        "Only these two forms go in double brackets — "
        "never a colour or a move alone like [[red]]. Every board_control call makes the student "
        "wait for a whole extra step, so call it only to change the position itself, all "
        "such changes in one step.\n\n"
        "GOLDEN RULE: If you are explaining a chess concept and the board is empty or "
        "shows an unrelated position, call get_topic FIRST — it puts a verified example on "
        "the board (the site's own lesson when there is one) — then explain exactly that "
        "position. Never describe or build an example position from memory: a wrong piece "
        "on a wrong square is worse than no example. If no tool has an example, explain on "
        "the current board or offer a puzzle (get_puzzle).\n\n"
        "### Lichess/Chess.com Game Loading Workflow\n"
        "When the user asks to find, load, or show a game from Lichess or Chess.com:\n"
        "1. Call lichess_game_import or chesscom_game_import with the username and max_games=1\n"
        "2. The result includes last_games with pgn field — take the PGN from there\n"
        "3. Call board_control with action_type=\"load_pgn\" and pgn=<the PGN from step 2>\n"
        "Never say you cannot load the game — always follow this 2-step workflow.\n"
        "If the student gives a LINK to a game (lichess.org/…, chess.com/game/…), call "
        "import_game_from_url with that link instead of the username import, then load_pgn.\n\n"
        "### Study programme — get_learning_path / get_lesson / training_recommender\n"
        "The site has a real programme (courses → modules → lessons with exercises "
        "and puzzles) and records the student's progress in it. When the student asks "
        "what to study, what comes next, about a course or lesson, or how to fix a "
        "weakness: read the programme with these tools and recommend REAL lessons by "
        "title with their url — never invent courses or lessons. To teach a lesson, "
        "call get_lesson: it puts the lesson's exercise on the board as a puzzle itself; "
        "explain the lesson's content in your own words and guide the student through that "
        "exercise. Ask get_user_progress only for statistics.\n\n"
        "### Knowledge base — get_topic / list_topics\n"
        "Before explaining or showing a chess concept (a tactic, a pawn structure, a typical "
        "position, an opening idea, an endgame technique) call get_topic: it returns the "
        "summary, key ideas, typical mistakes and puzzle themes, and PUTS AN EXAMPLE ON THE "
        "BOARD itself — from the site's lesson on the topic when there is one, else a "
        "verified position of the base — described in its `example` field. Teach from that "
        "example: say what is on the board as the FEN shows it, draw the plan with arrows, "
        "then OFFER a puzzle — set it up (get_puzzle(theme=…)) only when the student asks, "
        "never in the same answer, or the board jumps away from the example you are "
        "explaining. When get_topic lists `site_lessons`, the site's own lessons are the "
        "student's programme and come FIRST: teach from the lesson's task on the board, name "
        "the lesson and its course exactly as returned, and END the answer by inviting the "
        "student to go through that lesson and solve its tasks, with its url — before any "
        "example of the base or any get_puzzle. When the example carries `explanation`, that is the "
        "lesson's own text from the programme: teach in its words. list_topics shows the whole map when "
        "the student asks what they could learn. Never invent example positions.\n\n"
        "### analyze_position\n"
        "Use Stockfish for position evaluation. When the turn context has an \"Engine "
        "analysis of the board\" block, that IS Stockfish's result for the current "
        "position: answer from it and do not call analyze_position for that position "
        "again — call the engine only for a different position or a deeper look at a "
        "specific line.\n\n"
        "### check_moves\n"
        "Verify any specific move you suggest that did not come from the engine block or "
        "analyze_position/compare_variations output with check_moves before "
        "recommending it — never suggest an illegal move.\n\n"
        "CRITICAL: Your training data is outdated. The database has games "
        "through April 2026 including the FIDE Candidates 2026. ALWAYS search "
        "before claiming a tournament hasn't happened or a player has no games. "
        "If a search returns 0 results, try again with fewer/broader filters "
        "before giving up."
    )

    # How the coach talks, and the answer length rule (config.COACH_ANSWER_STYLE);
    # static, so they stay cached.
    sections.append(COACH_SPEECH_LAYER)
    brief = answer_style_layer()
    if brief:
        sections.append(brief)

    # ── Volatile suffix ────────────────────────────────────────────────
    # Everything below changes turn-to-turn (or day-to-day) and therefore
    # trails the static prefix above so it never busts the cached prefix.
    static_end = len(sections)

    # Current date so the model knows what year it is
    now = datetime.now(timezone.utc)
    sections.append(
        f"## Current Date\nToday is {now.strftime('%B %d, %Y')}. "
        "Use this when interpreting time references in user queries."
    )

    # Fire-and-forget rating sync for linked platform accounts
    if user_profile:
        maybe_sync_ratings(user_profile.user_id)

    # User context
    if user_profile:
        context = user_profile.to_prompt_context()
        if context:
            sections.append(f"## Student Profile\n{context}")

    sections.extend(_student_context_blocks(user_profile, board_fen, move_history))

    # Board context
    board_lines = []
    if board_fen:
        board_lines.append(f"Current position (FEN): {board_fen}")
        # Auto-inject structured tactical board analysis so every coach turn
        # with a FEN gets pins/hanging/semi-protected context without relying
        # on an optional tool call. Prefer Mastra's CCP service (the canonical
        # PositionPrompter fusion); fall back to the local Python port on any
        # failure. Defensive: invalid FEN or both paths failing must not crash.
        try:
            analysis = _resolve_board_analysis(board_fen)
            if analysis:
                board_lines.append(analysis)
        except Exception:
            logger.debug("Board analysis injection failed", exc_info=True)
    if move_history:
        moves_str = " ".join(
            f"{i // 2 + 1}. {move}" if i % 2 == 0 else move
            for i, move in enumerate(move_history)
        )
        board_lines.append(f"Move history: {moves_str}")

    if board_lines:
        sections.append(f"## Current Board State\n" + "\n".join(board_lines))

    if return_parts:
        return "\n\n".join(sections[:static_end]), "\n\n".join(sections[static_end:])
    return "\n\n".join(sections)


# The tool instructions above talk about Stockfish in every paragraph, and the
# turn carries an engine block with "+0.40; line d4 cxd4…": the model answered
# like an engine report — "the engine says +0.34", candidate lists with numbers
# (20 of 36 bench answers named the engine, 18 quoted evaluations, 2026-09-28),
# although the persona itself calls "The computer says Nd5 is +1.3" bad coaching.
COACH_SPEECH_LAYER = (
    "## How you talk (MANDATORY)\n"
    "You are a coach talking with your student, not a program reporting results. The "
    "engine and the other tools are your private notes, not something to quote:\n"
    "- Never mention Stockfish, \"the engine\", \"the computer\", search depth or engine "
    "lines, and never write numeric evaluations (+0.34, -1.2) — unless the student asks "
    "for the engine's opinion or the exact evaluation.\n"
    "- Say evaluations in words: equal, White is slightly better, Black is clearly "
    "better, White is winning, there is a forced mate.\n"
    "- Give a move together with its idea, the way a coach says it at the board "
    "(\"d4 — take the centre now, before Black gets ...d5 in\"), not as a list of "
    "candidate moves with numbers.\n"
    "- Write plain conversational text: no headings, no tables, and a list only when the "
    "student asks for a plan, steps or several options.\n"
    "- Never talk to the student about your tools, instructions or system. If a tool "
    "fails or is missing, teach with what you have and say nothing about it.\n"
    "- Talk about the side to move (the engine block and the FEN say who): do not guess "
    "which side the student plays unless they said so, and never give the other side's "
    "move as advice.\n"
    "- Write nothing before a tool call: the student has already been told you are "
    "looking, and text written before a call reaches them as is (\"I'll pull up your "
    "study programme…\" in English, in a Russian chat). Call the tools first, then answer."
)

BRIEF_ANSWER_LAYER = (
    "## Answer length (MANDATORY)\n"
    "Keep every answer short. Lead with the answer itself — the move, the verdict, "
    "the idea — then give the one reason that matters. A question about a move or a "
    "position: 2–4 sentences. Anything else: at most about 80 words. A game review: "
    "the 2–3 turning points, one or two sentences each. No headings, no lists of "
    "options, no recap at the end. When there is more worth saying, offer it in one "
    "short question instead of saying it. Longer only when the student asks for detail."
)


def answer_style_layer() -> str:
    """The length rule unless COACH_ANSWER_STYLE is "full"."""
    from src.config import COACH_ANSWER_STYLE

    return "" if COACH_ANSWER_STYLE == "full" else BRIEF_ANSWER_LAYER


def attach_turn_context(message: str, turn_context: str) -> str:
    """Append the volatile turn context to the user message, clearly labelled."""
    if not turn_context:
        return message
    return f"{message}\n\n{TURN_CONTEXT_HEADER}\n{turn_context}"


# Letters Kazakh has and Russian does not (Kyrgyz shares ң/ө/ү, but the coach
# speaks Russian, Kazakh and English only).
_KAZAKH_LETTERS = frozenset("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
# Chess notation is Latin but not English: "Nf3", "e4", "O-O", "Kxe5".
_NOTATION_TOKEN = re.compile(r"^(?:[KQRBNOkqrbn]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?[+#]?|O-O(?:-O)?|0-0(?:-0)?)$")


# Kazakh words spelt with Russian letters only («Мен не ойнауым керек?» has no
# ә/қ/ң): two of them make a Kazakh message.
_KAZAKH_WORDS = frozenset(
    "мен сен керек және болады болды болса емес ойнау ойнаймын ойнадым ойнайды ойнаса неге иә енді кейін деген "
    "дейді менің сенің маған саған осында сондықтан жасау жасаймын алу алады беру береді жүр жүру жүрем жүрді "
    "кім қай нені несі болу бар екен барма жеңу жеңді жеңемін ұтты".split())


def _script_language(message: str) -> Optional[str]:
    """The language *message* is written in, by its script — or None when it
    carries no language of its own (a move, a FEN, "ok").

    Words are counted, not letters: "Explain Сицилианская защита please" is
    English with a Russian name in it. A tie goes to the first word."""
    text = message or ""
    if any(ch in _KAZAKH_LETTERS for ch in text):
        return "kk"
    cyr_words = re.findall(r"[А-Яа-яЁё][А-Яа-яЁё-]*", text)
    if sum(1 for w in cyr_words if w.lower().replace("ё", "е") in _KAZAKH_WORDS) >= 2:
        return "kk"
    latin_words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+#=x'-]*", text) if not _NOTATION_TOKEN.match(w)]
    latin = sum(len(w) for w in latin_words if len(w) >= 2)
    n_cyr = sum(1 for w in cyr_words if len(w) >= 2)
    n_lat = sum(1 for w in latin_words if len(w) >= 2)
    if not n_cyr and not cyr_words:
        return "en" if latin >= 4 else None
    if n_cyr > n_lat:
        return "ru"
    if n_lat > n_cyr:
        return "en" if latin >= 4 else "ru"
    first = re.search(r"[A-Za-zА-Яа-яЁё]", text)
    if first and "A" <= first.group(0).upper() <= "Z" and latin >= 4:
        return "en"
    return "ru"


def _locale_code(locale: Optional[str]) -> str:
    code = (locale or "ru").lower()
    return code if code in LOCALE_TO_LANGUAGE else "ru"


# ── An explicit request for a language ────────────────────────────────────
#
# «Говори по-русски», "answer in English please", «қазақша сөйле»: the student
# names a language next to a word that asks for it. «Как по-английски будет
# вилка?» names a language too, but asks for a word, not a switch — such
# phrases are excluded; so is a negated one («не по-английски», "don't speak
# English"). The last language named and asked for wins.
_LANGUAGE_WORDS = [
    ("ru", r"по[\s-]?русски|на\s+русск(?:ом|ий)|к\s+русскому|русск(?:ий|им)\s+язык\w*|язык\w*\s*[:—–-]?\s*русск\w+|"
           r"russian|орысша"),
    ("en", r"по[\s-]?английски|на\s+английск(?:ом|ий)|к\s+английскому|английск(?:ий|им)\s+язык\w*|"
           r"язык\w*\s*[:—–-]?\s*английск\w+|english(?!\s+(?:opening|attack|defen))|ағылшынша"),
    ("kk", r"по[\s-]?казахски|на\s+казахск(?:ом|ий)|к\s+казахскому|казахск(?:ий|им)\s+язык\w*|"
           r"язык\w*\s*[:—–-]?\s*казахск\w+|kazakh|қазақша|казахша"),
]
# A whole message that is only a language: «по-русски!», "RU please", «рус», "eng".
_SHORT_LANGUAGE = {
    "ru": {"ru", "rus", "рус", "русский", "russian", "по-русски", "по русски", "на русском"},
    "en": {"en", "eng", "англ", "английский", "english", "по-английски", "на английском"},
    "kk": {"kk", "kz", "kaz", "каз", "қаз", "казахский", "kazakh", "қазақша", "казахша", "по-казахски", "на казахском"},
}
_SHORT_FILLER = {"please", "пожалуйста", "давай", "давайте", "only", "только", "now", "теперь", "язык", "language",
                 "на", "по", "in", "pls", "плз", "ок", "ok", "а", "и", "ну", "так", "and", "so", "then", "дальше"}
# Languages the coach does not speak: the request is noticed, not followed.
_OTHER_LANGUAGES = [
    ("German", r"по[\s-]?немецки|на\s+немецк\w+|немецк\w+\s+язык\w*|german|deutsch"),
    ("French", r"по[\s-]?французски|на\s+французск\w+|french|français"),
    ("Spanish", r"по[\s-]?испански|на\s+испанск\w+|spanish|español"),
    ("Italian", r"по[\s-]?итальянски|на\s+итальянск\w+|italian"),
    ("Chinese", r"по[\s-]?китайски|на\s+китайск\w+|chinese"),
    ("Turkish", r"по[\s-]?турецки|на\s+турецк\w+|turkish"),
    ("Ukrainian", r"по[\s-]?украински|на\s+украинск\w+|ukrainian"),
    ("Uzbek", r"по[\s-]?узбекски|на\s+узбекск\w+|uzbek"),
    ("Kyrgyz", r"по[\s-]?кыргызски|по[\s-]?киргизски|на\s+к[ыи]ргызск\w+|kyrgyz"),
    ("Tatar", r"по[\s-]?татарски|на\s+татарск\w+|tatar"),
    ("Arabic", r"по[\s-]?арабски|на\s+арабск\w+|arabic"),
    ("Japanese", r"по[\s-]?японски|на\s+японск\w+|japanese"),
    ("Korean", r"по[\s-]?корейски|на\s+корейск\w+|korean"),
    ("Polish", r"по[\s-]?польски|на\s+польск\w+|polish"),
    ("Portuguese", r"по[\s-]?португальски|на\s+португальск\w+|portuguese"),
    ("Hindi", r"на\s+хинди|hindi"),
]
_OTHER_LANGUAGE = [(name, re.compile(rf"(?<![а-яa-zәғқңөұүһі])(?:{pat})(?![а-яa-zәғқңөұүһі])", re.IGNORECASE))
                   for name, pat in _OTHER_LANGUAGES]
_LANGUAGE_WORD = [(code, re.compile(rf"(?<![а-яa-zәғқңөұүһі])(?:{pat})(?![а-яa-zәғқңөұүһі])", re.IGNORECASE))
                  for code, pat in _LANGUAGE_WORDS]
_B = r"(?<![а-яa-zәғқңөұүһі])"
_E = r"(?![а-яa-zәғқңөұүһі])"
_ASK_WORDS = (
    # Russian: speak / answer / write / switch / let's / may I / only / please …
    r"говори(?:те)?|отвечай(?:те)?|пиши(?:те)?|разговаривай(?:те)?|общайся|общайтесь|"
    r"объясняй(?:те)?|объясни(?:те)?|комментируй(?:те)?|рассказывай(?:те)?|"
    r"перейди(?:те)?|переходи(?:те)?|перейд[её]м|перейти|переключи(?:сь|тесь|ться)?|переключаемся|"
    r"вернись|вернитесь|верн[её]мся|вернуться|обратно|снова|опять|теперь|дальше|продолжаем|переходим|перехожу|"
    r"продолжай(?:те)?|продолжим|давай(?:те)?|можно|можешь|можете|мог(?:ла|ли)?\s+бы|"
    r"только|пожалуйста|лучше|хочу|хотелось\s+бы|предпочитаю|"
    r"смени(?:те)?|поменяй(?:те)?|измени(?:те)?|выбери(?:те)?|поставь(?:те)?|установи(?:те)?|"
    r"говорить|отвечать|писать|общаться|разговаривать|объяснять|язык\w*|"
    # English
    r"speak|talk|answer|reply|respond|write|switch|continue|explain|comment|communicate|"
    r"use|chat|go\s+on|carry\s+on|let'?s|please|can\s+you|could\s+you|would\s+you|only|"
    r"prefer|want|rather|stick\s+to|keep|stay|language|back\s+to|again|now|from\s+now\s+on|"
    # Kazakh
    r"сөйле(?:ңіз|ші|ңізші)?|жауап\s+бер(?:іңіз|ші|іңізші)?|жаз(?:ыңыз|шы|ыңызшы)?|"
    r"түсіндір(?:іңіз|ші)?|айт(?:ыңыз|шы)?|өтінемін|өтініш|болсын|ауыс\w*|көш\w*|жалғастыр\w*|тіл\w*"
)
_ASKS = re.compile(_B + "(?:" + _ASK_WORDS + ")" + _E, re.IGNORECASE)
# A language named to ask for a word or a translation, not for a switch: the
# construct must be tied to the language word («как по-английски будет вилка»,
# "how do you say fork in Russian", "the Russian word for"), not anywhere in
# the window — "Please answer in Russian: what is a skewer?" asks for Russian.
_NOT_A_SWITCH = re.compile(
    r"(?:(?:как|что\s+значит|что\s+означает|называ\w*|будет|перев\w*|сказать|звучит|означа\w*|значит|слово|термин)"
    r"[^.?!]{0,30}?(?:по[\s-]?(?:русски|английски|казахски)|на\s+(?:русск|английск|казахск)\w+)"
    r"|(?:по[\s-]?(?:русски|английски|казахски))\s+(?:будет|называ\w*|значит|звучит|это)"
    r"|(?:how\s+do\s+you\s+say|how\s+to\s+say|what\s+is|what'?s|what\s+does|called|translat\w*|means?|word\s+for|term\s+for)"
    r"[^.?!]{0,40}?\bin\s+(?:russian|english|kazakh)"
    r"|(?:russian|english|kazakh)\s+(?:word|term|name|translation|equivalent)\b)", re.IGNORECASE)
# «не говори по-английски», "don't speak English", «не по-английски», "not in
# English": a negation right before the language word (one word may sit between).
_NEGATED_BEFORE = re.compile(
    _B + r"(?:не|нет|ни|перестань(?:те)?|хватит|прекрати(?:те)?|никогда|don'?t|do\s+not|stop|never|not|no|quit)"
    r"\s+(?:[\wәғқңөұүһі'-]+\s+)?$", re.IGNORECASE)
_WINDOW = 45


def _short_language(text: str) -> Optional[str]:
    """«по-русски!», "RU please", «рус»: a message that is nothing but a language."""
    words = [w for w in re.split(r"[\s,.!?;:()«»\"']+", text.lower().replace("ё", "е")) if w]
    if not words or len(words) > 3:
        return None
    found = None
    for w in words:
        code = next((c for c, names in _SHORT_LANGUAGE.items() if w in names), None)
        if code:
            found = code
        elif w not in _SHORT_FILLER:
            return None
    return found


def other_language_request(message: str) -> Optional[str]:
    """The name of a language the coach does not speak, when *message* asks for it."""
    text = (message or "")[:4000]
    for name, rx in _OTHER_LANGUAGE:
        for m in rx.finditer(text):
            window = text[max(0, m.start() - _WINDOW): m.end() + _WINDOW]
            if _ASKS.search(window) and not _NOT_A_SWITCH.search(window) \
                    and not _NEGATED_BEFORE.search(text[max(0, m.start() - 30): m.start()]):
                return name
    return None


def language_request(message: str) -> Optional[str]:
    """The language the student asks the coach to speak in *message*
    ('ru', 'en', 'kk'), or None when the message asks for none."""
    text = (message or "")[:4000]
    short = _short_language(text)
    if short:
        return short
    found = None
    for code, rx in _LANGUAGE_WORD:
        for m in rx.finditer(text):
            window = text[max(0, m.start() - _WINDOW): m.end() + _WINDOW]
            if not _ASKS.search(window) or _NOT_A_SWITCH.search(window):
                continue
            if _NEGATED_BEFORE.search(text[max(0, m.start() - 30): m.start()]):
                continue
            if found is None or m.start() > found[0]:
                found = (m.start(), code)
    return found[1] if found else None


def conversation_language(user_messages, locale: Optional[str] = None) -> tuple[str, str]:
    """The language the coach answers in next, and why.

    *user_messages* are the student's messages, newest first (for a chat turn,
    the current one first). Returns a locale code and one of: "asked" — the
    student asked for this language (the most recent request holds until the
    next one); "message" — the language of their latest message that has one;
    "interface" — the interface language, as nothing else decides. The move
    comments of a game, which answer no message, use the same choice.
    """
    newest_script = None
    other = None
    for i, text in enumerate(user_messages):
        asked = language_request(text)
        if asked:
            return asked, "asked"
        if i == 0:
            other = other_language_request(text)
        if newest_script is None:
            newest_script = _script_language(text)
    if other:
        # A language the coach does not speak, asked for just now: the answer
        # says so and goes on in the language that would have been used.
        return (newest_script or _locale_code(locale)), f"unsupported:{other}"
    if newest_script:
        return newest_script, "message"
    return _locale_code(locale), "interface"


def reply_language(message: str, locale: Optional[str] = None) -> str:
    """The language to answer *message* in: the one it asks for, its own script, else the interface locale."""
    return LOCALE_TO_LANGUAGE[conversation_language([message], locale)[0]]


# Kazakh chess terms the coach must use (stand, 2026-10-04: the bishop came out
# as «пияз», an onion). The accepted Russian loanword is given in brackets where
# students use it too; the preferred Kazakh word comes first.
KAZAKH_TERMS = (
    "Kazakh chess terms — use exactly these: king — патша (король); queen — уәзір (ферзь); rook — тура (ладья); "
    "bishop — піл (слон), never «пияз»; knight — ат (конь); pawn — сарбаз (пешка); check — шах; checkmate — мат; "
    "stalemate — пат; castling — рокировка; move — жүріс; capture — алу/жеу; attack — шабуыл; defend — қорғау; "
    "fork — айыр (вилка); pin — байлау (связка); discovered check — ашық шах; double check — қос шах; "
    "White/Black — ақтар/қаралар; centre — орталық; kingside/queenside — патша қанаты/уәзір қанаты; "
    "board — тақта; file/rank/diagonal — тік/көлденең/диагональ; opening/middlegame/endgame — дебют/миттельшпиль/эндшпиль."
)


def kazakh_terms_note(code: Optional[str]) -> str:
    """The terms line when the answer is in Kazakh, else ""."""
    return KAZAKH_TERMS if (code or "").lower() in ("kk", "kz") else ""


_LANGUAGE_WHY = {
    "asked": "the language the student asked for; keep it until they ask otherwise",
    "message": "the language of the student's message",
    "interface": "the student's interface language",
}


def language_note(code: str, why: str = "message") -> str:
    """The last line of a text turn for a language already chosen (see reply_language_note);
    in Kazakh it carries the chess terms too."""
    note = _language_note_core(code, why)
    terms = kazakh_terms_note(code)
    return note[:-1] + f" {terms}]" if terms else note


def _language_note_core(code: str, why: str = "message") -> str:
    language = LOCALE_TO_LANGUAGE.get(code, "Russian")
    if why.startswith("unsupported:"):
        other = why.split(":", 1)[1]
        return (f"[Reply language: the student asked you to speak {other}, which you do not speak — say so in one "
                f"short sentence (you speak Russian, Kazakh and English) and write the whole answer in {language}. "
                f"Never switch to another language.]")
    return (f"[Reply language: write your whole answer in {language} — {_LANGUAGE_WHY.get(why, _LANGUAGE_WHY['message'])}. "
            f"Never switch to another language.]")


def spoken_language_note(code: str, why: str) -> str:
    """One sentence for the voice prompt: the language this session is in.

    The spoken coach gets no per-turn note; at the token mint it learns what
    the session already decided (prompt_builder.conversation_language) — a
    language the student asked for, in text or aloud, or the one they have
    been using. "" when only the interface locale decides (the rule covers it).
    """
    language = LOCALE_TO_LANGUAGE.get(code, "Russian")
    if why.startswith("unsupported:"):
        return (f"The student asked for {why.split(':', 1)[1]}, which you do not speak: say so once, briefly, "
                f"and speak {language}.")
    if why == "asked":
        return (f"The student has asked you to speak {language}: speak {language} from your first word, "
                f"whatever language they use now, until they ask otherwise.")
    if why == "message":
        return f"The conversation so far has been in {language}: start in {language}."
    return ""


def reply_language_note(message: str, locale: Optional[str] = None, history=()) -> str:
    """The last line of every text turn: the language of this answer.

    The language rule leads a long system prompt; after the history, the turn
    context and tool results DeepSeek once answered a Russian question in
    Chinese (2026-09-29). A reminder at the very end of the turn holds.
    *history*: the student's earlier messages, newest first — a language they
    asked for earlier in the session still holds.
    """
    return language_note(*conversation_language([message, *history], locale))


def question_moves(message: str, fen: Optional[str]) -> list[dict]:
    """The moves the student names — in notation («Rg1», «Лd8») or in words
    («поставить ладью на g1», "take on h4 with the rook") — each with its
    verdict on the board: ``san``, ``verdict``, ``legal``, ``move`` (a
    chess.Move when legal), ``after_fen``, ``source`` ('san' or 'prose'),
    ``words``. [] when the message names no move or there is no board."""
    if not fen or not message:
        return []
    import chess

    from src.answer_check import _MOVE, _to_san
    from src.move_words import prose_moves

    try:
        board = chess.Board(fen)
    except ValueError:
        return []
    if not board.is_valid():
        return []
    out: list[dict] = []
    seen: set[str] = set()

    def _add(san: str, source: str, words: str = "", note: Optional[str] = None, move=None) -> None:
        if move is None:
            try:
                move = board.parse_san(san)
            except ValueError:
                move = None
        key = move.uci() if move is not None else san
        if key in seen:
            return
        seen.add(key)
        verdict = note or _move_verdict(board, san)
        item = {"san": board.san(move) if move is not None else san, "verdict": verdict, "legal": move is not None,
                "move": move, "after_fen": None, "source": source, "words": words}
        if move is not None:
            after = board.copy(stack=False)
            after.push(move)
            item["after_fen"] = after.fen()
        out.append(item)

    converted, _ = _to_san(message)
    for m in _MOVE.finditer(converted):
        san = m["san"]
        if san[0] not in "KQRBNO" and not m["num"] and not m["bdots"]:
            continue  # a bare square («e4») is not a move the student names
        _add(san, "san")
    for pm in prose_moves(message, board):
        _add(pm["san"], "prose", pm["words"], pm["note"], pm["move"])
    # «Конь на f7 с вилкой — хорошая идея?»: a piece and a square with no verb is
    # a move in the student's words when such a move is legal (the coach's
    # answer is never read this loosely — there «конь на f7» names a piece).
    from src.move_words import _ptype, resolve

    for m in re.finditer(r"(?<![а-яa-z])(?P<piece>конь|ладья|слон|ферзь|король|пешка|knight|rook|bishop|queen|king|pawn)"
                         r"\s+(?:на|to|on|onto)\s+(?P<sq>[a-h][1-8])(?![0-9])", message.lower().replace("ё", "е")):
        ptype = _ptype(m["piece"])
        if ptype is None:
            continue
        san, move, _note = resolve(board, ptype, chess.parse_square(m["sq"]))
        if move is not None:
            _add(san, "prose", m.group(0), None, move)
    return out


def moves_in_question_block(message: str, fen: Optional[str], moves: Optional[list] = None) -> str:
    """The moves the student named, checked on the board before the model
    answers: «Могу ли я сыграть Rg1? А Qxg7?» came back "both are legal" with
    Qxg7 blocked by the f6 pawn (stand, 2026-10-04). Decided by python-chess,
    not by the model; "" when the message names no move or there is no board."""
    if moves is None:
        moves = question_moves(message, fen)
    if not moves:
        return ""
    import chess

    board = chess.Board(fen)
    lines = ["## Moves named in the question (checked on the board, side to move "
             f"{'White' if board.turn else 'Black'})"]
    for item in moves[:6]:
        words = f" («{item['words']}»)" if item.get("source") == "prose" and item.get("words") else ""
        line = f"- {item['san']}{words}: {item['verdict']}"
        if item.get("move") is not None:
            # What the piece does from its new square — python-chess, no engine, so
            # it is here even when the engine's look at the idea misses its wait.
            try:
                from src.hypothetical import moved_piece_facts

                after = board.copy(stack=False)
                after.push(item["move"])
                line += " — after it: " + "; ".join(moved_piece_facts(board, after, item["move"]))
            except Exception:  # noqa: BLE001
                pass
        lines.append(line)
    return "\n".join(lines)


def board_facts_block(fen: Optional[str]) -> str:
    """What hangs, what is attacked, what is pinned on the board — verified by
    python-chess, no engine, no best move. For a live game, where the engine
    line is withheld so the coach hints rather than tells (production,
    2026-10-05: the coach proposed Nf7 with the queen on h5 hanging to g6)."""
    if not fen:
        return ""
    try:
        import chess

        from src.position_facts import static_facts

        board = chess.Board(fen)
        if not board.is_valid():
            return ""
        facts = static_facts(board)
    except Exception:  # noqa: BLE001
        return ""
    if not facts:
        return ""
    return (
        "## Facts of the board (verified on the position, no engine)\n"
        + "\n".join(f"- {f}" for f in facts)
        + "\nAny move you mention must respect these: a piece listed as attacked and not defended is "
        "lost unless the move saves it; never propose a move that leaves your own queen or a piece "
        "hanging, and never claim an attack or a defence that is not here or on the board."
    )


def live_game_block(note: str) -> str:
    """The engine's look at a live game — evaluation and the opponent's threat, no best move."""
    return (
        "## Engine facts for the game (no best move for the student)\n"
        f"{note}\n"
        "Stockfish looked at this position: the evaluation is from White's side, the threat is verified. "
        "Say who stands better in words only — no numbers, no engine name — and warn about the threat "
        "when it matters. Do not name the best move for the student unless they insist twice: hint, as "
        "the game rules say. Never claim an attack, a threat or a defence that is not in the facts."
    )


def voice_idea_note(moves: list, hypo: Optional[dict], live_game: bool = False) -> Optional[str]:
    """The «[Idea] …» line for the live voice session: the move the student
    named, played on the board and judged by the engine (src/hypothetical.py),
    in the shape of the other voice lines ([Engine], [Topic], [Check])."""
    if not moves:
        return None
    named = []
    for item in moves[:4]:
        words = f" («{item['words']}»)" if item.get("source") == "prose" and item.get("words") else ""
        named.append(f"{item['san']}{words} — {item['verdict']}")
    parts = ["[Idea] The student names a move: " + "; ".join(named) + "."]
    if hypo and hypo.get("note"):
        lines = [ln.lstrip("- ").strip() for ln in hypo["note"].splitlines() if ln.strip()]
        parts.append("Played on the board and analysed by Stockfish: " + " ".join(lines))
    parts.append(
        "Judge the idea from these facts, in the student's language, without calling analyze_position "
        "or check_moves for these moves; never claim an attack, a capture, a check or a defence that is "
        "not listed here, and never read out numbers."
    )
    if live_game:
        parts.append("This is a live game: do not name a better move instead — say what happens after the idea.")
    return " ".join(parts)


def hypothetical_block(note: str, live_game: bool = False) -> str:
    """The student's idea played on the board and looked at by the engine
    (src/hypothetical.py), as a turn-context block."""
    tail = (
        "This is a live game: do not name a better move for the student instead — say what "
        "happens after their idea and let them look again."
        if live_game else
        "If the idea is a mistake, say what to play instead only from the engine analysis of "
        "the board above (or ask the engine); never from memory."
    )
    return (
        "## The student's idea, played on the board (engine)\n"
        f"{note}\n"
        "Stockfish played each move the student named and analysed the position after it; "
        "the facts are verified on that position. Judge the idea from them, in your own "
        "coaching words — what the moved piece really attacks and whether it is safe, what "
        "the opponent's best reply is and what it does — no engine name, no numbers. Never "
        "claim an attack, a threat, a capture or a defence that is not in these facts: "
        f"«ладья на g1 нападает на ферзя h4» is a claim about this position, check it here first. {tail}"
    )


def _move_verdict(board, san: str) -> str:
    import chess

    try:
        move = board.parse_san(san)
        return "legal" + (" — gives check" if board.gives_check(move) else "")
    except chess.AmbiguousMoveError:
        return "ambiguous — more than one piece can make it"
    except ValueError:
        pass
    other = board.copy(stack=False)
    other.turn = not board.turn
    try:
        other.parse_san(san)
        return f"NOT legal for the side to move; it is a move for {'White' if other.turn else 'Black'}"
    except ValueError:
        pass
    # Why not: the piece exists but the way is blocked, or no such piece reaches the square.
    if san.startswith("O-O"):
        return "NOT legal — castling is not available here"
    piece_letter = san[0] if san[0] in "KQRBN" else "P"
    ptype = chess.PIECE_SYMBOLS.index(piece_letter.lower())
    import re as _re

    dest_name = _re.findall(r"[a-h][1-8]", san)[-1]
    dest = chess.parse_square(dest_name)
    from src.answer_check import _geometry_move

    for sq in board.pieces(ptype, board.turn):
        if _geometry_move(ptype, sq, dest) and ptype != chess.KNIGHT:
            between = chess.SquareSet.between(sq, dest)
            blocker = next((b for b in between if board.piece_at(b) is not None), None)
            if blocker is not None:
                bp = board.piece_at(blocker)
                return (f"NOT legal — the {chess.piece_name(bp.piece_type)} on {chess.square_name(blocker)} "
                        f"is in the way of the {chess.piece_name(ptype)} on {chess.square_name(sq)}")
    target = board.piece_at(dest)
    if target is not None and target.color == board.turn:
        return f"NOT legal — your own {chess.piece_name(target.piece_type)} stands on {dest_name}"
    if board.is_check():
        return "NOT legal — the king is in check and this move does not answer it"
    return f"NOT legal — no {chess.piece_name(ptype)} of the side to move can reach {dest_name}"


def review_block(result: dict) -> str:
    """The game's critical moments, found by the server before the turn (see coach_chat).

    A game review used to spend its first model call (2-3.5 s on Gemini) only
    deciding to load the game and call find_critical_moments; the server does
    both the moment the message arrives.
    """
    moments = result.get("critical_moments") or []
    lines = [
        "## Critical moments of the student's game (engine, depth "
        f"{result.get('engine_depth', 12)}; evaluations from White's side)",
        "The game is ALREADY loaded on the student's board: do not load it again and do not "
        "call find_critical_moments for it.",
        f"Moves in the game: {result.get('total_moves', '?')}.",
    ]
    for m in moments:
        dots = "." if m.get("side") == "white" else "..."
        line = (f"- {m.get('move_number')}{dots}{m.get('move')} ({m.get('side')}, {m.get('type')}): "
                f"{m.get('eval_before'):+} → {m.get('eval_after'):+}")
        if m.get("best_move"):
            line += f". Better: {m['best_move']} (line {m.get('best_line', m['best_move'])})"
        if m.get("fen_before"):
            line += f". Position before the move: {m['fen_before']}"
        lines.append(line)
    if not moments:
        lines.append("- The engine found no swing of 1.5 pawns or more: a clean game.")
    lines.append(
        "Explain the turning points that matter most, in your own words: what went wrong and "
        "what was better. Set a position on the board only when you walk through one of them."
    )
    return "\n".join(lines)


def engine_note_block(note: str, opening: bool = False) -> str:
    """The turn's engine line (src/voice_engine_note.py) as a turn-context block.

    With *opening* the board shows the opening the student asked about (see
    src/opening_knowledge.py), so the block is part of that answer, not a
    position to ignore for a general opening question.
    """
    if opening:
        return (
            "## Engine analysis of the board (the opening line above, its final position)\n"
            f"{note}\n"
            "Stockfish analysed the position the opening line ends in; the moves are legal as "
            "written. Use it with the opening block to explain the line — what the last move "
            "threatens, what the best reply is — in your own coaching words: no engine name, no "
            "numbers. Its \"Facts\" part is verified; never claim an attack, a defence or a "
            "threat that is not in the facts, the lines or a tool result."
        )
    return (
        "## Engine analysis of the board\n"
        f"{note}\n"
        "Stockfish already analysed the current position for this turn; the moves are legal "
        "as written. Answer from it — do not call analyze_position or check_moves for these "
        "moves, and write any arrows as [[arrows: …]] marks in the answer itself. It is your "
        "private reference: tell the student what it means in your own coaching words — "
        "no engine name, no numbers. Its \"Facts\" part — what hangs, what is pinned, what "
        "the best move and the opponent threaten — is verified: explain WHY a move is good from "
        "those facts, and never claim an attack, a defence or a threat that is not in the facts, "
        "the lines or a tool result. Its \"Opening\" line is the ECO book's name for this "
        "position — use that name; without one, never name the opening from memory (call "
        "identify_opening with the moves if you have them). The board is sent with every "
        "message, so use this block "
        "only when the question is about this position; for anything else — what to study "
        "next, a concept, an opening in general, the student's games or progress — ignore it "
        "and answer that question with its own tools (get_learning_path, get_topic, …)."
    )


# Spoken-style adaptation layer: turns the shared SOUL persona into a live-voice
# coach. Kept as a constant so the single source of truth for the *persona* stays
# SOUL.md while the *spoken* delivery rules live here (mirrors the directives the
# live-token route used to hand-write, so voice behavior is preserved).
VOICE_STYLE_LAYER = (
    "## Speaking Style (voice mode)\n"
    "You are now speaking out loud in a live voice conversation — the same "
    "coach the player types with. Talk the way a coach sitting beside the board "
    "would:\n"
    "- Keep sentences short, natural, and conversational. NO markdown, NO bullet "
    "points, NO headings, NO long monologues — this is spoken, not written.\n"
    "- Refer to squares, pieces, threats, and simple plans out loud (e.g. "
    "\"the knight on d5\", \"the pawn on e4\").\n"
    "- Ask a short question when you're unsure what the player sees, rather than "
    "lecturing. Lead them to the idea instead of just handing over the move.\n"
    "- Never break character or say things like \"as a chess AI\".\n"
    "- The [Engine] line and the tool results are your private notes: never say "
    "\"the engine says\" and never read out numbers like \"plus zero point four\" — "
    "say in words who is better and why."
)

VOICE_TOOL_LAYER = (
    "## Tools (voice mode)\n"
    "You have the same tools as the text coach. Use them instead of guessing or "
    "inventing lines:\n"
    "- The current position: after the board changes the system may add a line "
    "starting with \"[Engine]\" — Stockfish's verified top moves for that FEN and "
    "\"Facts\": what hangs, what is pinned, what the best move and the opponent "
    "threaten, and the ECO book's name of the opening when it has one — never name an "
    "opening yourself. When it matches the current position, answer from it straight away, no "
    "tool call, and explain WHY from those facts — never name an attack, a defence or a "
    "threat that is not in them. Otherwise, or for any other position, call "
    "analyze_position.\n"
    "- A move the student names («а если Rg1?», «поставлю ладью на g1»): the system adds "
    "a line starting with \"[Idea]\" — that move played on the board and analysed: whether it "
    "is legal, what the piece really attacks from its new square, whether it can be taken, the "
    "opponent's best reply and how the evaluation changed. Judge the idea from that line, never "
    "from your head: «the rook on g1 attacks the queen on h4» is a claim about that position, "
    "and the line already says what the rook attacks.\n"
    "- Any move you name that did not come from the engine: verify it with "
    "check_moves first; if it is illegal, pick a legal move from the returned "
    "list — never speak an illegal move. A move you recommend is checked by the engine after "
    "you say it; if it loses, you will be told and must correct yourself.\n"
    "- A concept (a tactic, a pawn structure, an endgame technique, an opening "
    "idea): get_topic — it puts a verified example on the board itself (the "
    "site's lesson when there is one); describe exactly that position, and when "
    "it names a site lesson, send the student to that lesson's tasks at the end.\n"
    "- Puzzles: get_puzzle (theme + the student's rating) — it puts the puzzle "
    "on the board itself; never invent a puzzle.\n"
    "- Openings: identify_opening for the name, get_opening_stats for what is "
    "played. Master games: search_master_games (surname only) or "
    "find_games_by_position.\n"
    "- The student's own games: get_user_games; a game link → "
    "import_game_from_url; a Lichess/Chess.com username → lichess_game_import / "
    "chesscom_game_import; then board_control load_pgn.\n"
    "- What to study next: get_learning_path, get_lesson, training_recommender — "
    "name real lessons, never invented ones.\n"
    "- Show, don't only tell: board_control sets positions, draws arrows, "
    "highlights squares, steps through a game.\n"
    "CRITICAL for a live voice conversation: the moment you decide to call a "
    "tool, FIRST speak a brief spoken acknowledgment out loud (something like "
    "\"let me check that\" or \"one sec, looking now\") and THEN make the tool "
    "call. Never go silent while a tool runs — the player should always hear you "
    "respond right away.\n"
    "Examples of a concept (pin, fork, skewer…) come ONLY from get_topic or "
    "get_lesson, which put the position on the board themselves. Never set up an "
    "example position from memory.\n"
    "Say moves the way a person says them out loud (\"knight f3\", \"конь эф "
    "три\", \"ат эф үш\"), never as engine notation like \"g1f3\"."
)


def build_voice_prompt(
    soul_content: str,
    user_profile: Optional[UserProfile] = None,
    board_fen: Optional[str] = None,
    locale: Optional[str] = None,
    tools_available: bool = True,
    language: Optional[tuple[str, str]] = None,
) -> str:
    """Build the spoken system prompt for the Gemini Live voice coach.

    Renders from the SAME sources as the text prompt so the two modes can't
    drift: the SOUL.md persona core, then a spoken-style adaptation layer (short
    sentences, no markdown, speak-before-tool-call), the student profile, and a
    compact current-position line. Deliberately omits the heavy tactical board
    analysis the text path injects — voice minting is latency-sensitive and the
    spoken coach reads the board out loud rather than from an analysis dump.

    Args:
        soul_content: The SOUL.md persona text (single source of truth).
        user_profile: Optional profile for personalization (rating/goals/weaknesses).
        board_fen: Optional current FEN to anchor the conversation.
        locale: Optional UI locale code ('ru', 'kz', 'en').
        tools_available: Include the spoken tool-use directives (default True).
        language: The session's (language code, why) from conversation_language —
            what the student asked for, or has been writing in — so the spoken
            coach starts in it (see spoken_language_note).

    Returns:
        Complete spoken system prompt string.
    """
    sections = []

    # Same mandatory language directive the text prompt leads with, then what
    # this session already decided.
    if locale:
        rule = language_rule(locale)
        note = spoken_language_note(*language) if language else ""
        terms = kazakh_terms_note(language[0] if language else locale)
        sections.append(" ".join(part for part in (rule, note, terms) if part))

    # Persona core (shared with text) + spoken delivery overrides.
    sections.append(soul_content.rstrip())
    sections.append(VOICE_STYLE_LAYER)

    # Student profile — same context text chat gets (Task 2 parity).
    if user_profile:
        context = user_profile.to_prompt_context()
        if context:
            sections.append(f"## Student Profile\n{context}")

    # Same memory the text coach reads (mistakes, own games, playbook, focus).
    # Built once per voice session at token mint, so it costs no per-turn time.
    sections.extend(_student_context_blocks(user_profile, board_fen))

    # Compact current-position anchor (no tactical-analysis injection).
    if board_fen:
        sections.append(
            "## Current Board State\n"
            f"The current position (FEN) is: {board_fen}. Refer to it when relevant."
        )

    if tools_available:
        sections.append(VOICE_TOOL_LAYER)

    return "\n\n".join(sections)
