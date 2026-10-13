-- ============================================================================
-- 20261013_052_puzzle_rush_school.sql
-- Puzzle Rush school / branch ranking (P2 backend) — Chesster survival runs are
-- pushed to Chess Empire `survival_scores` (CE students-api) by
-- backend/services/puzzle_rush_school.py.
--
--  • puzzle_rush_runs.school_* — the push outcome per run, so it can be shown
--    and retried: school_push_status is pushed | not_best | unlinked |
--    needs_student | error; school_student_id is the CE student the run was
--    (or would be) pushed for; school_pushed_at is set once CE accepted it.
--  • puzzle_rush_school_pick — a family account's remembered student pick
--    (pre-selected next time; every run still needs an explicit claim).
--    user_id is the Clerk user id (TEXT, same as puzzle_rush_runs.user_id).
--
-- Security model: same server-only lockdown as 049 (RLS on, REVOKE from
-- anon/authenticated); all access goes through the Flask service role.
--
-- Idempotent: safe to re-run. NOT applied to prod (separate approval step);
-- until it is, Flask logs and skips saving the outcome / pick.
-- ============================================================================

BEGIN;

ALTER TABLE puzzle_rush_runs ADD COLUMN IF NOT EXISTS school_student_id UUID;
ALTER TABLE puzzle_rush_runs ADD COLUMN IF NOT EXISTS school_push_status TEXT;
ALTER TABLE puzzle_rush_runs ADD COLUMN IF NOT EXISTS school_pushed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS puzzle_rush_school_pick (
  user_id              TEXT PRIMARY KEY,           -- Clerk user id
  external_student_id  UUID NOT NULL,              -- CE student id
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE puzzle_rush_school_pick ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON puzzle_rush_school_pick FROM anon, authenticated;

COMMIT;
