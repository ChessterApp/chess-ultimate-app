# Spec: Multi-Move Puzzle Support (Levels 3–5)

## Problem
`lesson_puzzles` only stores the FIRST move of each puzzle (`solution_move`, single UCI string). The Lichess study import scripts (`backend/scripts/import_lichess_study.py`, `import_level3_puzzles.py`, `import_level4*.py`, `import_level5*.py`) parsed full PGN mainlines but kept only `moves[0]`. Frontend (`AnimatedChessBoard`, `PuzzleSequence`) completes the puzzle after one matched move. Levels 3+ contain mate-in-2 / mate-in-3 puzzles that require: user move → auto opponent reply → user move → … until the line is exhausted.

DB state (checked 2026-07-08): 1,883 puzzles total; 1,576 have a lichess study chapter `source_url` (full lines recoverable by re-fetch); 307 have no source.

## Tasks

### Task 1: Schema migration
- [x] Add `solution_line` column to `lesson_puzzles` — JSONB (or TEXT storing JSON array) of UCI moves in order: user move, opponent reply, user move, …
- [x] Keep `solution_move` unchanged (must always equal `solution_line[0]` when line present) for backward compatibility.
- [x] Follow the existing migration convention in the repo (see migration 005 that created `lesson_puzzles`).

### Task 2: Backfill script
- [ ] New script `backend/scripts/backfill_solution_lines.py`.
- [ ] For puzzles WITH `source_url`: group by study ID, fetch each study PGN ONCE from lichess (`https://lichess.org/api/study/{id}.pgn`), match chapters to puzzles (by FEN and/or chapter URL), parse the FULL mainline with python-chess, write `solution_line` (UCI array). Respect lichess rate limits: sequential requests, back off on 429, ~1 req/sec.
- [ ] For puzzles WITHOUT `source_url`: use Stockfish (already used elsewhere in backend/scripts) to check for a forced mate from the puzzle FEN; if a forced mate exists matching the stored `solution_move` as first move, generate the full forced line and store it. Otherwise store `solution_line = [solution_move]` and log the puzzle id to `backend/scripts/backfill_unresolved.log` for manual review.
- [ ] Script must be idempotent (skip puzzles that already have solution_line unless --force) and support --dry-run and --limit N for testing.
- [ ] Sanity check every written line: replay it with python-chess from the puzzle FEN — every move legal, first move equals `solution_move` (if it doesn't, prefer the study line and UPDATE solution_move too, logging the change).
- [ ] Run on a --limit 20 sample first, verify, then run the full backfill. Report final counts: lines written, unresolved, mismatched first moves.

### Task 3: Backend API
- [x] `backend/api/puzzles.py` (and any other endpoint serving lesson_puzzles): include `solution_line` in responses. If NULL, fall back to `[solution_move]` so the frontend always receives an array.
- [x] Update/add backend tests for the endpoint shape.

### Task 4: Frontend multi-move playback
- [x] `AnimatedChessBoard` (frontend): accept `solutionLine: string[]` (keep `solutionMove` prop working for old callers).
- [x] Logic: maintain a line index. User plays a move → if it matches the expected line move: if it's the last move of the line, fire success (existing celebration + onCorrectMove); otherwise auto-play the opponent's reply from the line after a short delay (~400-600ms) with the existing move animation, then wait for the user's next move. Wrong move → existing retry/incorrect feedback, board resets to the position before the wrong move (line index preserved).
- [x] `PuzzleSequence` passes solution_line through; puzzle counts as solved only when the full line is completed.
- [x] Handle promotions in UCI comparison (e.g. e7e8q).
- [x] Add unit tests for the line-validation logic (multi-move success, wrong move mid-line, single-move fallback).

### Task 5: Verification
- [ ] Run backend test suite and frontend test suite; all green (note pre-existing failures separately).
- [ ] `npm run build` in frontend must succeed. Do NOT deploy — deployment is done separately via deploy.sh by the operator.
- [ ] Print a summary: migration applied, backfill counts, tests passing.

## Constraints
- Never `git add -A`; add specific files. `export HOME=/root` before git commands.
- Do not delete or overwrite existing puzzle data; only add solution_line (and correct solution_move only when the study line disagrees, with logging).
- Supabase/Postgres credentials and connection setup: same as existing backend scripts use.
- Commit in logical chunks with conventional commit messages.
