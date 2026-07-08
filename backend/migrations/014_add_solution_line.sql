-- Migration: Add solution_line column to lesson_puzzles
-- Created: 2026-07-08
-- Description: Stores the FULL solution line for multi-move puzzles (mate-in-2/3, etc.)
--              as an ordered JSON array of UCI moves: user move, opponent reply,
--              user move, ...  solution_move remains the FIRST move for backward
--              compatibility (must equal solution_line[0] when a line is present).

BEGIN;

-- Ordered UCI moves for the full puzzle line.
-- JSONB array of strings, e.g. ["f1f6", "g8h8", "f6h6"].
-- NULL for puzzles not yet backfilled; the API falls back to [solution_move].
ALTER TABLE lesson_puzzles
ADD COLUMN IF NOT EXISTS solution_line JSONB;

COMMENT ON COLUMN lesson_puzzles.solution_line IS
  'Ordered UCI move list for multi-move puzzles (user, opponent, user, ...). solution_line[0] equals solution_move. NULL until backfilled.';

COMMIT;
