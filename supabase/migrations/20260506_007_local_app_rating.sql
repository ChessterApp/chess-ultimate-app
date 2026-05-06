-- Migration: Local App Rating — FIDE removal, OTB-only gating
--
-- Replaces the earlier FIDE-Elo scaffolding (20260428_004_ratings.sql) with a
-- single internal "Local App Rating" system. The rating is updated only when
-- a tournament is finalized AND is_rated=true AND tournament_mode='offline'.
--
-- Changes:
--   1. Drop player_fide_ratings (FIDE ID linkage table — no longer used).
--   2. Rename tournaments.is_fide_rated → tournaments.is_rated
--      (semantics: counts toward Local App Rating, not "FIDE-rated").
--   3. Add tournaments.tournament_mode (offline|online) — only offline counts.
--   4. Tighten rating_history.source_type to allow only 'tournament'.
--
-- player_ratings is left untouched — the (user, org) single-rating shape is
-- already correct.

-- 1. Drop the FIDE rating table.
DROP TABLE IF EXISTS player_fide_ratings CASCADE;

-- 2. Rename is_fide_rated → is_rated on tournaments.
ALTER TABLE tournaments RENAME COLUMN is_fide_rated TO is_rated;

-- 3. Add tournament_mode (offline|online) with default 'offline'.
ALTER TABLE tournaments
  ADD COLUMN tournament_mode TEXT NOT NULL DEFAULT 'offline'
    CHECK (tournament_mode IN ('offline', 'online'));

-- Existing rows backfill to 'offline' via the DEFAULT; explicit UPDATE for safety.
UPDATE tournaments SET tournament_mode = 'offline' WHERE tournament_mode IS NULL;

-- 4. Tighten rating_history.source_type — only 'tournament' is now allowed.
ALTER TABLE rating_history DROP CONSTRAINT IF EXISTS rating_history_source_type_check;
ALTER TABLE rating_history ADD CONSTRAINT rating_history_source_type_check
  CHECK (source_type IN ('tournament'));
