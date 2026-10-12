-- ============================================================================
-- 20261012_049_puzzle_rush.sql
-- Puzzle Rush Phase 1 — run / attempt / personal-best storage
-- (/root/clawd/memory/reference/puzzle-rush-ux-spec.md §5.2, §5.3, §7).
--
--  • puzzle_rush_runs — one row per run. The Flask engine owns the clock
--    (started_at is the end of the 3-2-1 countdown, deadline_at = started_at +
--    180/300 s, NULL for survival) and all state transitions. Guests (§7.6) have
--    user_id NULL and authenticate every call with a random token whose SHA-256
--    lives in guest_token_hash; guest runs never touch bests or leaderboards.
--    move_seq is a compare-and-set counter so racing requests can't double-apply.
--    seed makes the ramp/selection reproducible per run.
--  • puzzle_rush_attempts — one row per served puzzle (PK run_id, idx). Holds the
--    user's UCI moves for review; the solution line is NOT stored here, it is read
--    from the puzzles SQLite DB server-side and only exposed once a run has ended.
--  • puzzle_rush_bests — cached PB per (user_id, mode); ties keep the earlier run.
--    display_name is a best-effort Clerk name snapshot so boards never call Clerk.
--
-- Security model: all three tables are server-only (RLS on, REVOKE from
-- anon/authenticated — the 20260918_042 / 044 lockdown pattern). Every read and
-- write goes through the Flask service role; runs carry the selection seed and
-- guest token hashes, which clients must not see.
--
-- Idempotent: safe to re-run (IF NOT EXISTS). NOT applied to prod (separate
-- approval step).
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS puzzle_rush_runs (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                TEXT,                      -- Clerk user id; NULL = guest
  guest_token_hash       TEXT,                      -- sha256 of the guest token
  display_name           TEXT,
  mode                   TEXT NOT NULL CHECK (mode IN ('3min','5min','survival')),
  seed                   TEXT NOT NULL,
  started_at             TIMESTAMPTZ NOT NULL,
  deadline_at            TIMESTAMPTZ,               -- NULL for survival
  last_activity_at       TIMESTAMPTZ NOT NULL,
  ended_at               TIMESTAMPTZ,
  end_reason             TEXT CHECK (end_reason IN ('strikes','timeout','quit','abandoned')),
  score                  INT NOT NULL DEFAULT 0,
  strikes                INT NOT NULL DEFAULT 0,
  current_streak         INT NOT NULL DEFAULT 0,
  longest_streak         INT NOT NULL DEFAULT 0,
  highest_solved_rating  INT,
  avg_ms_per_puzzle      INT,
  duration_ms            INT,
  puzzle_count           INT NOT NULL DEFAULT 0,    -- puzzles served so far
  move_seq               INT NOT NULL DEFAULT 0,
  is_new_pb              BOOLEAN NOT NULL DEFAULT false,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT puzzle_rush_runs_owner CHECK (user_id IS NOT NULL OR guest_token_hash IS NOT NULL),
  CONSTRAINT puzzle_rush_runs_end CHECK ((ended_at IS NULL) = (end_reason IS NULL))
);

-- Leaderboards by period (§5.3).
CREATE INDEX IF NOT EXISTS idx_puzzle_rush_runs_board
  ON puzzle_rush_runs (mode, ended_at, score);
-- Best Today / personal top-10 / stale-run sweep per user.
CREATE INDEX IF NOT EXISTS idx_puzzle_rush_runs_user
  ON puzzle_rush_runs (user_id, mode, ended_at) WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS puzzle_rush_attempts (
  run_id         UUID NOT NULL REFERENCES puzzle_rush_runs(id) ON DELETE CASCADE,
  idx            INT  NOT NULL,
  puzzle_id      TEXT NOT NULL,
  puzzle_rating  INT  NOT NULL,
  result         TEXT NOT NULL DEFAULT 'unfinished' CHECK (result IN ('solved','failed','unfinished')),
  user_moves     TEXT NOT NULL DEFAULT '',          -- space-separated UCI
  served_at      TIMESTAMPTZ NOT NULL,
  answered_at    TIMESTAMPTZ,
  ms             INT,
  PRIMARY KEY (run_id, idx)
);

CREATE TABLE IF NOT EXISTS puzzle_rush_bests (
  user_id       TEXT NOT NULL,
  mode          TEXT NOT NULL CHECK (mode IN ('3min','5min','survival')),
  best_score    INT  NOT NULL,
  best_run_id   UUID REFERENCES puzzle_rush_runs(id) ON DELETE SET NULL,
  display_name  TEXT,
  achieved_at   TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (user_id, mode)
);

CREATE INDEX IF NOT EXISTS idx_puzzle_rush_bests_board
  ON puzzle_rush_bests (mode, best_score DESC, achieved_at);

-- ============================================================================
-- Row Level Security — server-only lockdown.
-- ============================================================================
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['puzzle_rush_runs','puzzle_rush_attempts','puzzle_rush_bests'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON %I FROM anon, authenticated;', t);
  END LOOP;
END $$;

COMMIT;
