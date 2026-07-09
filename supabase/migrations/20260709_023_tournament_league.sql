-- Migration: League tier column on tournaments.
--
-- League C registration gate (spec: league-c-level-gate). Adds a nullable
-- `league` classification to tournaments. League C tournaments require the
-- registering student to be at Chess Empire Level 2 or higher; the eligibility
-- check lives in backend/services/tournament_service.register_player.
--
-- NULL = no league (default, behavior unchanged). Idempotent; safe to re-run.

ALTER TABLE tournaments
  ADD COLUMN IF NOT EXISTS league TEXT
    CHECK (league IN ('C', 'B', 'A', 'Master'));

-- ROLLBACK (commented):
-- ALTER TABLE tournaments DROP COLUMN IF EXISTS league;
