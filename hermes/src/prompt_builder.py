"""System prompt builder — combines persona, user profile, and board state.

Assembles the full system prompt for the AI agent from:
1. SOUL.md (chess coach persona)
2. User profile (rating, goals, weaknesses, style)
3. Current board state (FEN, move history if PGN loaded)
4. Available tools summary
5. Platform ratings (auto-synced from linked accounts)
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from src.user_profile import UserProfile

logger = logging.getLogger(__name__)


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
    "en": "English",
}


def build_system_prompt(
    soul_content: str,
    user_profile: Optional[UserProfile] = None,
    board_fen: Optional[str] = None,
    move_history: Optional[list[str]] = None,
    locale: Optional[str] = None,
) -> str:
    """Build the full system prompt for the chess coaching agent.

    Args:
        soul_content: The SOUL.md persona text.
        user_profile: Optional user profile for personalization.
        board_fen: Optional current board FEN position.
        move_history: Optional list of SAN moves played so far.
        locale: Optional UI locale code (e.g. 'ru', 'kz', 'en').

    Returns:
        Complete system prompt string.
    """
    sections = []

    # Inject mandatory language directive before everything else
    if locale and locale != "en":
        language_name = LOCALE_TO_LANGUAGE.get(locale, locale)
        sections.append(
            f"CRITICAL LANGUAGE RULE: You MUST respond entirely in {language_name}. "
            f"All explanations, questions, and chess commentary must be in {language_name}. "
            "This is non-negotiable — never switch to English unless the user explicitly writes in English."
        )

    sections.append(soul_content.rstrip())

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

    # Board context
    board_lines = []
    if board_fen:
        board_lines.append(f"Current position (FEN): {board_fen}")
    if move_history:
        moves_str = " ".join(
            f"{i // 2 + 1}. {move}" if i % 2 == 0 else move
            for i, move in enumerate(move_history)
        )
        board_lines.append(f"Move history: {moves_str}")

    if board_lines:
        sections.append(f"## Current Board State\n" + "\n".join(board_lines))

    # Tool instructions
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
        "- **set_fen**: Set a position on the board. Use whenever explaining a concept, "
        "tactic, or strategic idea. Construct clear example positions for pins, forks, "
        "skewers, discovered attacks, etc.\n"
        "- **load_pgn**: Load a full game on the board. Use when referencing master games "
        "so the student can replay the moves.\n"
        "- **draw_arrows**: Highlight key lines, threats, and tactical patterns. "
        "Use green for good moves, red for threats, blue for alternatives.\n"
        "- **highlight_squares**: Mark important squares — outposts, weak squares, "
        "targets, key central squares.\n"
        "- **set_puzzle**: Present a tactical puzzle for the student to solve.\n"
        "- **navigate**: Move forward/back through a loaded game.\n"
        "- **flip_board**: Flip the board perspective.\n"
        "- **clear_board**: Reset the board.\n\n"
        "GOLDEN RULE: If you are explaining a chess concept and the board is empty or "
        "shows an unrelated position, SET UP an example position FIRST, then explain. "
        "Never describe a position in words alone.\n\n"
        "### analyze_position\n"
        "Use Stockfish for position evaluation.\n\n"
        "CRITICAL: Your training data is outdated. The database has games "
        "through April 2026 including the FIDE Candidates 2026. ALWAYS search "
        "before claiming a tournament hasn't happened or a player has no games. "
        "If a search returns 0 results, try again with fewer/broader filters "
        "before giving up."
    )

    return "\n\n".join(sections)
