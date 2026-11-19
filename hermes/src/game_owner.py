"""Whose game a saved game is — the student's own, someone else's, or not known (tester's report 18.11).

The daily plan's card «Разбор последней партии» showed DrNykterstein – Night-King96: a game the tester had opened in
the Database section and saved («Сохранить в Мои партии»). A saved game is a row of the student's ``user_games`` like
any game they played; the card took the latest row, its request said «Разбери мою последнюю партию», and the review
told it as theirs — «нападением на твоего ферзя».

What the server knows exactly, strongest first:

1. **The student's linked accounts** (``user_chess_profiles.lichess_username`` / ``chesscom_username``, the
   link_platform tool): a game of Lichess or Chess.com is the student's when one of its players is one of those names
   — and the side is that player's colour — and someone else's when neither is. An over-the-board game typed in with
   real names is not judged by an online name.
2. **Where the row came from** (``user_games.source``, set by the site and the app when they save): a game of a
   collection opened in the Database section — the master base (``twic``), a shared base (``shared``, ``database``)
   — is someone else's; a game with the coach (``coach_game``) is the student's.
3. **A game of Lichess or Chess.com with no linked account** (``lichess``, ``chesscom``): the Database section's
   «Lichess» / «Chess.com» tab lists the games of whatever nickname is typed — the student saves their OWN games that
   way, and someone else's (the tester's DrNykterstein – Night-King96) exactly the same way. Whose it is is not known
   («saved»): the card still offers it, but as «the last saved game», and the review names the sides by colour and
   the players' names, never «ты», until the student says which side they played (Asan, 19.11: their own games must
   not vanish from the card for a student who has not linked an account).
4. Anything else — a pasted or imported game (``manual``, ``local_import``, ``board_entry``, ``user``, none) — is not
   known either way, and is treated as before: the student's.

The card offers only a game not known to be someone else's; a review of someone else's game (the student may still
open it from «Мои партии» and ask) is told about the players — «белые», «Carlsen» — never «ты», «твой».
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import chess

logger = logging.getLogger(__name__)

# The sources of a row saved from a collection of the Database section (site src/app/database/page.tsx
# handleSaveToMyGames, the app's app/database/[gameId].tsx viewerSource): a game the student opened, not one they played.
COLLECTION_SOURCES = frozenset({"twic", "master", "database", "shared", "shared-link"})
# Games of the online platforms: the ones a linked username can tell.
PLATFORM_SOURCES = frozenset({"lichess", "chesscom"})
OWN_SOURCES = frozenset({"coach_game"})


@dataclass(frozen=True)
class Owner:
    """``verdict``: own | foreign | saved (a platform game, whose not known) | unknown; ``color``: the student's side
    when known (chess.WHITE / chess.BLACK); ``why``: what decided it, in a few words."""

    verdict: str
    color: Optional[bool] = None
    why: str = ""

    @property
    def foreign(self) -> bool:
        return self.verdict == "foreign"

    @property
    def neutral(self) -> bool:
        """No side of the game is the student's to the coach: someone else's game, or one whose owner is not known."""
        return self.verdict in ("foreign", "saved")


def _name(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def linked_names(user_id: Optional[str]) -> Optional[set]:
    """The student's linked Lichess / Chess.com usernames (casefolded); an empty set when none is linked, None when
    they could not be read."""
    if not user_id:
        return set()
    try:
        from src.platform_linking import _get_chess_profile

        row = _get_chess_profile(user_id)
    except Exception:  # noqa: BLE001 — not read: nothing is decided by names
        logger.debug("linked names not read", exc_info=True)
        return None
    row = row if isinstance(row, dict) else {}
    return {_name(row.get(k)) for k in ("lichess_username", "chesscom_username") if _name(row.get(k))}


def owner(game: Optional[dict], names: Optional[set] = None) -> Owner:
    """Whose game the ``user_games`` row *game* is, given the student's linked *names* (None: not known)."""
    if not isinstance(game, dict):
        return Owner("unknown")
    source = _name(game.get("source"))
    if source in OWN_SOURCES:
        return Owner("own", why="a game the student played with the coach")
    white, black = _name(game.get("white")), _name(game.get("black"))
    if names:
        if white and white in names:
            return Owner("own", chess.WHITE, f"White is their linked account {game.get('white')}")
        if black and black in names:
            return Owner("own", chess.BLACK, f"Black is their linked account {game.get('black')}")
        if source in PLATFORM_SOURCES:
            return Owner("foreign", why=f"a {source} game and neither player is their linked account")
    if source in COLLECTION_SOURCES:
        return Owner("foreign", why="a game of a collection opened in the Database section and saved to their games")
    if source in PLATFORM_SOURCES:
        return Owner("saved", why=f"a {source} game saved from the Database section; no linked {source} account tells "
                                  "whether the student played it")
    return Owner("unknown")


def offered(game: Optional[dict], names: Optional[set] = None) -> bool:
    """The daily plan may offer *game* as «your last game»: it is not known to be someone else's."""
    return not owner(game, names).foreign


def review_block(game: Optional[dict], who: Owner) -> str:
    """Whose game is being reviewed, for the turn: "" when not known (as before)."""
    if not isinstance(game, dict) or who.verdict == "unknown":
        return ""
    white, black = str(game.get("white") or "?"), str(game.get("black") or "?")
    if who.foreign:
        return (
            "## Whose game this is (decided by the server)\n"
            f"This game is NOT the student's own: {white} (White) – {black} (Black) — {who.why}. The student did not "
            "play it, whatever their message calls it («мою партию»): review it as a game to learn from. Name the "
            "sides by colour or by the players' names («белые», «чёрные», «" + white + "») — never «ты», «твой», «у "
            "тебя», «сен», \"you\", \"your\" for a side of it, and no «где ты ошибся». Do not argue about whose game "
            "it is and do not mention this note."
        )
    if who.verdict == "saved":
        return (
            "## Whose game this is (decided by the server)\n"
            f"It is NOT known whether the student played this game: {white} (White) – {black} (Black) — {who.why}. "
            "Whatever their message calls it («мою партию»), name the sides by colour or by the players' names "
            "(«белые», «чёрные», «" + white + "»), never «ты», «твой», «у тебя», «сен», \"you\", \"your\" for a side of "
            "it, until the student says which side they played; you may ask it once, in one short question at the end. "
            "Do not mention this note."
        )
    if who.color is None:
        return ""
    side, other = ("White", "Black") if who.color == chess.WHITE else ("Black", "White")
    return (
        "## Whose game this is (decided by the server)\n"
        f"The student played {side} in this game ({who.why}): «ты», «твой», \"you\" mean {side}; {other} is the "
        "opponent."
    )


def game_row(user_id: Optional[str], game_id: Optional[str]) -> Optional[dict]:
    """The players and the origin of one of the student's saved games, or None."""
    try:
        from src.tools.user_data import _GAME_ID_RE, _supabase_query

        if not user_id or not isinstance(game_id, str) or not _GAME_ID_RE.match(game_id):
            return None
        rows = _supabase_query("user_games", {
            "id": f"eq.{game_id}", "user_id": f"eq.{user_id}", "deleted_at": "is.null",
            "select": "id,white,black,source", "limit": "1",
        })
    except Exception:  # noqa: BLE001 — not read: the review goes on as before
        logger.debug("game row not read", exc_info=True)
        return None
    return rows[0] if rows and isinstance(rows[0], dict) else None


def review_owner(user_id: Optional[str], game_id: Optional[str]) -> tuple[Optional[dict], Owner]:
    """(the row, whose it is) for a review of the saved game *game_id* (the plan card's review_game_id)."""
    row = game_row(user_id, game_id)
    if row is None:
        return None, Owner("unknown")
    return row, owner(row, linked_names(user_id))
