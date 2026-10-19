"""
Tug of War puzzle packs — read-only picks from the Lichess puzzles SQLite DB.

A pack is `count` distinct puzzles from a level's rating band (or a band around a
target rating, widened when it runs dry), optionally
restricted to puzzles tagged with ANY of `themes`. Selection is
PuzzleSource.pick_in_band (services/puzzle_rush_source.py): the same connection,
quality filter and index seeks as Puzzle Rush.

Unthemed packs follow the DB's natural theme mix (~50% mate-in-1 at Pawn — kept
on purpose). Themed packs pick a requested theme uniformly per puzzle, so a
multi-theme selection gets a mix rather than being swamped by the commonest tag.

Lichess `fen` is BEFORE the opponent setup move moves[0]. Packs apply it and
return the solving position plus the remaining line (solver plays even indices),
which is the TugPuzzle shape the frontend plays directly.
"""

import random

import chess

from services.puzzle_rush_source import PuzzleSource, get_puzzle_source

LEVEL_BANDS = {
    'pawn': (400, 800),
    'knight': (800, 1200),
    'rook': (1200, 1600),
    'queen': (1600, 2400),
}
THEMES = frozenset({
    'mateIn1', 'mateIn2', 'fork', 'pin', 'skewer', 'backRankMate', 'discoveredAttack', 'hangingPiece',
})
DEFAULT_COUNT = 60
MAX_COUNT = 120
MAX_EXCLUDE = 1000
RATING_MIN, RATING_MAX = 400, 2800
SPREAD_MIN, SPREAD_MAX, DEFAULT_SPREAD = 25, 400, 75
WIDEN_TRIES = 3


def to_solving_position(puzzle: dict) -> dict:
    """Apply the setup move: the returned fen has the solver to move."""
    board = chess.Board(puzzle['fen'])
    board.push_uci(puzzle['moves'][0])
    return {
        'id': puzzle['id'],
        'fen': board.fen(),
        'moves': puzzle['moves'][1:],
        'rating': puzzle['rating'],
        'themes': puzzle['themes'],
    }


def pack(level: str, themes=(), count: int = DEFAULT_COUNT, exclude=(),
         source: PuzzleSource | None = None, rng: random.Random | None = None) -> list[dict]:
    """Up to `count` distinct solving-position puzzles from a level's band."""
    lo, hi = LEVEL_BANDS[level]
    return pack_band(lo, hi, themes, count, exclude, source, rng)


def rating_band(rating: int, spread: int) -> tuple[int, int]:
    return max(RATING_MIN, rating - spread), min(RATING_MAX, rating + spread)


def pack_rating(rating: int, spread: int = DEFAULT_SPREAD, themes=(), count: int = DEFAULT_COUNT, exclude=(),
                source: PuzzleSource | None = None, rng: random.Random | None = None) -> list[dict]:
    """A pack around `rating`; a band that runs dry widens (spread x2, up to WIDEN_TRIES times)."""
    source = source or get_puzzle_source()
    rng = rng or random.Random()
    out = []
    served = list(exclude)
    for _ in range(WIDEN_TRIES + 1):
        lo, hi = rating_band(rating, spread)
        out += pack_band(lo, hi, themes, count - len(out), served, source, rng)
        if len(out) >= count:
            break
        served = list(exclude) + [p['id'] for p in out]
        spread *= 2
    return out


def pack_band(lo: int, hi: int, themes=(), count: int = DEFAULT_COUNT, exclude=(),
              source: PuzzleSource | None = None, rng: random.Random | None = None) -> list[dict]:
    """Up to `count` distinct solving-position puzzles rated lo..hi (fewer only if the filter runs dry)."""
    source = source or get_puzzle_source()
    rng = rng or random.Random()
    served = list(dict.fromkeys(exclude))
    open_themes = list(dict.fromkeys(themes))
    out = []
    while len(out) < count:
        if themes:
            if not open_themes:
                break
            theme = rng.choice(open_themes)
            puzzle = source.pick_in_band(lo, hi, served, rng, theme)
            if puzzle is None:
                open_themes.remove(theme)
                continue
        else:
            puzzle = source.pick_in_band(lo, hi, served, rng)
            if puzzle is None:
                break
        served.append(puzzle['id'])
        out.append(to_solving_position(puzzle))
    return out
