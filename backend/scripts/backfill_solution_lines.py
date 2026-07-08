#!/usr/bin/env python3
"""
Backfill solution_line for lesson_puzzles.

Populates the `solution_line` column (added in migration 014) with the FULL
ordered UCI move list for each puzzle: user move, opponent reply, user move, ...

Resolution sources, tried per puzzle in this order:

  1. training_puzzle URL  (lichess.org/training/<id>)
       -> GET /api/puzzle/<id>, use the `solution` UCI list directly.
  2. study_chapter URL    (lichess.org/study/<studyId>/<chapterId>)
       -> parse the study PGN (fetched once per study). If the study export is
          blocked (403 for private studies), fall back to the per-chapter PGN
          endpoint which stays public.
  3. study_only / practice URL  (lichess.org/study/<id>, lichess.org/practice/<id>)
       -> parse the study PGN, match the chapter by FEN.
  4. Stockfish fallback (no URL, unfetchable URL, or no chapter match)
       -> if a forced mate exists from the FEN whose first move matches the
          stored solution_move, generate the full forced line.

Anything unresolved is stored as [solution_move] (normalised to UCI) and logged
to backfill_unresolved.log for manual review.

Every written line is replayed with python-chess from the puzzle FEN: every move
must be legal. If the resolved line's first move disagrees with the stored
solution_move we PREFER the resolved line and UPDATE solution_move too, logging
the change.

Usage:
    python backfill_solution_lines.py [--dry-run] [--limit N] [--force]

Options:
    --dry-run   Resolve and report but write nothing.
    --limit N   Only process the first N candidate puzzles (for testing).
    --force     Re-resolve puzzles that already have solution_line.
"""

import argparse
import io
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import chess.pgn
import chess.engine
from supabase import create_client

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/usr/games/stockfish")
STOCKFISH_DEPTH = 20
LICHESS_HEADERS = {
    "Accept": "application/x-chess-pgn",
    "User-Agent": "ChessterBackfill/1.0 (Educational; lesson puzzle backfill)",
}
REQUEST_DELAY = 1.0  # seconds between lichess requests (respect rate limits)
UCI_RE = re.compile(r"^[a-h][1-8][a-h][1-8][qrbnQRBN]?$")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UNRESOLVED_LOG = os.path.join(SCRIPT_DIR, "backfill_unresolved.log")


def load_env():
    env_path = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def get_supabase():
    load_env()
    url = os.environ.get("SUPABASE_URL", "https://qtzujwiqzbgyhdgulvcd.supabase.co")
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
    )
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY not found in environment")
    return create_client(url, key)


# --------------------------------------------------------------------------- #
# Chess helpers
# --------------------------------------------------------------------------- #

def normalize_fen(fen):
    """First 4 FEN fields (placement, turn, castling, en passant)."""
    return " ".join(fen.split()[:4])


def solution_move_to_uci(fen, solution_move):
    """Normalise a stored solution_move (UCI or SAN) to UCI for the given FEN."""
    if not solution_move:
        return None
    try:
        board = chess.Board(fen)
    except Exception:
        return None
    sm = solution_move.strip()
    if UCI_RE.match(sm):
        try:
            mv = chess.Move.from_uci(sm.lower())
            if mv in board.legal_moves:
                return mv.uci()
        except Exception:
            pass
    try:
        return board.parse_san(sm).uci()
    except Exception:
        return None


def replay_legal(fen, ucis):
    """Return True if every UCI move is legal replayed from fen."""
    if not ucis:
        return False
    try:
        board = chess.Board(fen)
    except Exception:
        return False
    for u in ucis:
        try:
            mv = chess.Move.from_uci(u)
        except Exception:
            return False
        if mv not in board.legal_moves:
            return False
        board.push(mv)
    return True


def uci_line_from_game(game):
    """Return (start_fen, [uci, ...]) for a python-chess game's mainline."""
    board = game.board()
    ucis = [mv.uci() for mv in game.mainline_moves()]
    return board.fen(), ucis


def chapter_id_from_url(url):
    m = re.search(r"/study/[^/]+/([^/?#]+)", url or "")
    return m.group(1) if m else None


def study_id_from_url(url):
    m = re.search(r"/(?:study|practice)/([^/?#]+)", url or "")
    return m.group(1) if m else None


def training_id_from_url(url):
    m = re.search(r"/training/([^/?#]+)", url or "")
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# Lichess fetching (rate-limited, cached)
# --------------------------------------------------------------------------- #

class Lichess:
    def __init__(self):
        self.session = requests.Session()
        self.study_cache = {}   # study_id -> list[chapter dict] | None
        self.chapter_cache = {}  # (study_id, chapter_id) -> [uci] | None
        self.puzzle_cache = {}  # puzzle_id -> [uci] | None

    def _get(self, url, accept_pgn=True):
        headers = dict(LICHESS_HEADERS)
        if not accept_pgn:
            headers["Accept"] = "application/json"
        for attempt in range(5):
            try:
                resp = self.session.get(url, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                backoff = 3 * (attempt + 1)
                print(f"    network error on {url}: {e}; retrying in {backoff}s")
                time.sleep(backoff)
                continue
            if resp.status_code == 429:
                backoff = 5 * (attempt + 1)
                print(f"    429 rate limited on {url}; backing off {backoff}s")
                time.sleep(backoff)
                continue
            time.sleep(REQUEST_DELAY)
            return resp
        return None

    def _parse_study_pgn(self, text):
        chapters = []
        stream = io.StringIO(text)
        while True:
            try:
                game = chess.pgn.read_game(stream)
            except Exception:
                break
            if game is None:
                break
            try:
                start_fen, ucis = uci_line_from_game(game)
            except Exception:
                continue
            site = game.headers.get("Site", "") or game.headers.get("ChapterURL", "")
            chapters.append({
                "chapter_id": chapter_id_from_url(site),
                "norm_fen": normalize_fen(start_fen),
                "ucis": ucis,
            })
        return chapters

    def study_chapters(self, study_id):
        """Fetch and cache the full study PGN as a list of chapters. None if blocked."""
        if study_id in self.study_cache:
            return self.study_cache[study_id]
        url = f"https://lichess.org/api/study/{study_id}.pgn"
        resp = self._get(url)
        chapters = None
        if resp is not None and resp.status_code == 200 and "chess-pgn" in resp.headers.get("content-type", ""):
            chapters = self._parse_study_pgn(resp.text)
        else:
            code = resp.status_code if resp is not None else "err"
            print(f"    study {study_id} export unavailable ({code})")
        self.study_cache[study_id] = chapters
        return chapters

    def chapter_line(self, study_id, chapter_id):
        """Fetch a single chapter PGN (works even when full-study export is blocked)."""
        key = (study_id, chapter_id)
        if key in self.chapter_cache:
            return self.chapter_cache[key]
        url = f"https://lichess.org/study/{study_id}/{chapter_id}.pgn"
        resp = self._get(url)
        ucis = None
        if resp is not None and resp.status_code == 200 and "chess-pgn" in resp.headers.get("content-type", ""):
            chapters = self._parse_study_pgn(resp.text)
            if chapters:
                ucis = chapters[0]["ucis"]
        self.chapter_cache[key] = ucis
        return ucis

    def puzzle_solution(self, puzzle_id):
        if puzzle_id in self.puzzle_cache:
            return self.puzzle_cache[puzzle_id]
        url = f"https://lichess.org/api/puzzle/{puzzle_id}"
        resp = self._get(url, accept_pgn=False)
        sol = None
        if resp is not None and resp.status_code == 200:
            try:
                sol = resp.json().get("puzzle", {}).get("solution")
            except Exception:
                sol = None
        self.puzzle_cache[puzzle_id] = sol
        return sol


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def match_chapter(chapters, chapter_id, norm_fen, expected_uci):
    """Pick the best chapter line for a puzzle."""
    if not chapters:
        return None
    # 1. exact chapter id
    if chapter_id:
        for c in chapters:
            if c["chapter_id"] == chapter_id and c["ucis"]:
                return c["ucis"]
    # 2. FEN match (disambiguate by first move if several)
    fen_matches = [c for c in chapters if c["norm_fen"] == norm_fen and c["ucis"]]
    if len(fen_matches) == 1:
        return fen_matches[0]["ucis"]
    if len(fen_matches) > 1 and expected_uci:
        for c in fen_matches:
            if c["ucis"][0] == expected_uci:
                return c["ucis"]
    if fen_matches:
        return fen_matches[0]["ucis"]
    return None


def resolve_from_lichess(puzzle, lichess, expected_uci):
    """Try to resolve the line from lichess. Returns (ucis|None, source_str)."""
    url = puzzle.get("source_url") or ""
    fen = puzzle["fen"]
    norm = normalize_fen(fen)

    training_id = training_id_from_url(url)
    if training_id:
        sol = lichess.puzzle_solution(training_id)
        if sol and replay_legal(fen, sol):
            return sol, "training"
        return None, "training"

    study_id = study_id_from_url(url)
    if not study_id:
        return None, "no_source"

    chapter_id = chapter_id_from_url(url)

    # Prefer the full study export (one request per study).
    chapters = lichess.study_chapters(study_id)
    line = match_chapter(chapters, chapter_id, norm, expected_uci)
    if line and replay_legal(fen, line):
        return line, "study"

    # Study export blocked but we know the chapter -> per-chapter endpoint.
    if chapter_id:
        line = lichess.chapter_line(study_id, chapter_id)
        if line and replay_legal(fen, line):
            return line, "chapter"

    return None, "study"


def resolve_from_stockfish(fen, expected_uci, engine):
    """Return a forced-mate line whose first move is expected_uci, else None."""
    if engine is None:
        return None
    try:
        board = chess.Board(fen)
    except Exception:
        return None
    if board.is_game_over():
        return None
    limit = chess.engine.Limit(depth=STOCKFISH_DEPTH)
    try:
        info = engine.analyse(board, limit)
    except Exception:
        return None
    score = info["score"].pov(board.turn)
    if not score.is_mate() or score.mate() <= 0:
        return None

    line = []
    b = board.copy()
    for _ in range(2 * score.mate() + 2):
        if b.is_game_over():
            break
        try:
            res = engine.play(b, limit)
        except Exception:
            return None
        if res.move is None:
            break
        line.append(res.move.uci())
        b.push(res.move)
        if b.is_checkmate():
            break
    if not b.is_checkmate():
        return None
    if expected_uci and line and line[0] != expected_uci:
        return None
    return line


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def fetch_candidates(supabase, force):
    """Fetch all puzzles that need a solution_line, paginated."""
    rows = []
    page = 0
    size = 1000
    while True:
        q = supabase.table("lesson_puzzles").select(
            "id, fen, solution_move, solution_line, source_url"
        ).order("id").range(page * size, page * size + size - 1)
        result = q.execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < size:
            break
        page += 1
    if not force:
        rows = [r for r in rows if r.get("solution_line") is None]
    return rows


def main():
    parser = argparse.ArgumentParser(description="Backfill solution_line for lesson_puzzles")
    parser.add_argument("--dry-run", action="store_true", help="Resolve but write nothing")
    parser.add_argument("--limit", type=int, help="Only process the first N candidates")
    parser.add_argument("--force", action="store_true", help="Re-resolve puzzles that already have solution_line")
    args = parser.parse_args()

    supabase = get_supabase()
    candidates = fetch_candidates(supabase, args.force)
    if args.limit:
        candidates = candidates[: args.limit]

    print(f"Candidates to process: {len(candidates)}")
    if not candidates:
        print("Nothing to do.")
        return

    lichess = Lichess()
    engine = None
    if os.path.exists(STOCKFISH_PATH):
        try:
            engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        except Exception as e:
            print(f"Warning: could not start Stockfish ({e}); mate fallback disabled")
    else:
        print(f"Warning: Stockfish not found at {STOCKFISH_PATH}; mate fallback disabled")

    counts = {"written": 0, "unresolved": 0, "mismatched": 0, "multi_move": 0}
    unresolved_entries = []

    try:
        for i, puzzle in enumerate(candidates, 1):
            pid = puzzle["id"]
            fen = puzzle["fen"]
            sm = puzzle.get("solution_move")
            expected = solution_move_to_uci(fen, sm)

            line, source = resolve_from_lichess(puzzle, lichess, expected)

            if not line:
                sf_line = resolve_from_stockfish(fen, expected, engine)
                if sf_line:
                    line, source = sf_line, "stockfish"

            if not line:
                # Fallback: single move (normalised to UCI when possible).
                fallback = expected or (sm if sm else None)
                if fallback:
                    line, source = [fallback], "fallback"
                    counts["unresolved"] += 1
                    unresolved_entries.append(f"{pid}\t{source}\t{fen}\t{sm}")
                else:
                    counts["unresolved"] += 1
                    unresolved_entries.append(f"{pid}\tunparseable\t{fen}\t{sm}")
                    print(f"[{i}/{len(candidates)}] {pid}: UNRESOLVED (unparseable solution_move)")
                    continue

            # Sanity: replay must be fully legal.
            if not replay_legal(fen, line):
                counts["unresolved"] += 1
                unresolved_entries.append(f"{pid}\tillegal_replay\t{fen}\t{sm}")
                print(f"[{i}/{len(candidates)}] {pid}: line failed replay, skipping")
                continue

            # First-move agreement / correction.
            update_solution_move = None
            if expected and line[0] != expected and source not in ("fallback",):
                # Genuine disagreement -> prefer resolved line, correct solution_move.
                update_solution_move = line[0]
                counts["mismatched"] += 1
                unresolved_entries.append(
                    f"{pid}\tmismatch_fixed\t{fen}\twas={sm}({expected}) now={line[0]}"
                )

            if len(line) > 1:
                counts["multi_move"] += 1

            tag = "MULTI" if len(line) > 1 else "single"
            print(f"[{i}/{len(candidates)}] {pid}: {source} {tag} len={len(line)} {line[:4]}"
                  + (f"  (fix solution_move -> {update_solution_move})" if update_solution_move else ""))

            if not args.dry_run:
                update = {"solution_line": line}
                if update_solution_move:
                    update["solution_move"] = update_solution_move
                supabase.table("lesson_puzzles").update(update).eq("id", pid).execute()
                counts["written"] += 1
    finally:
        if engine is not None:
            try:
                engine.quit()
            except Exception:
                pass  # engine may already be dead; nothing to clean up

    if unresolved_entries:
        with open(UNRESOLVED_LOG, "a") as f:
            for e in unresolved_entries:
                f.write(e + "\n")

    print("\n" + "=" * 50)
    print("Backfill summary" + (" (DRY RUN)" if args.dry_run else ""))
    print("=" * 50)
    print(f"  Candidates processed : {len(candidates)}")
    print(f"  Lines written        : {counts['written']}")
    print(f"  Multi-move lines     : {counts['multi_move']}")
    print(f"  Unresolved (fallback): {counts['unresolved']}")
    print(f"  solution_move fixed  : {counts['mismatched']}")
    if unresolved_entries:
        print(f"  Details logged to    : {UNRESOLVED_LOG}")


if __name__ == "__main__":
    main()
