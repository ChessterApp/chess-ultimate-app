-- Migration 012: Coach game insights (CL Phase 1, Slice 2 — retrieval over the
-- student's own games).
--
--   coach_game_insights — one distilled row per reviewed game. The Game Review
--     engine pipeline (backend/services/game_review.py) computes per-move engine
--     ground truth on demand and never persists it; this table captures the
--     durable digest of a completed review (opening, result, accuracy, the worst
--     blunders/mistakes, a short plain-text summary) so the coach can retrieve a
--     student's own recent games and reason over them.
--
-- Deliberately NO vector store / embeddings in this slice: at <100 games per
-- student, recency + structured filters (opening, theme, result) beat cosine
-- similarity. An `embedding` column can be added later without reshaping this
-- table. Additive only; idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS coach_game_insights (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  game_ref TEXT,                          -- id in user_games/games, or review_id
  source TEXT,                            -- e.g. 'review'
  color TEXT,
  opening TEXT,
  result TEXT,
  accuracy NUMERIC,
  blunders JSONB NOT NULL DEFAULT '[]',   -- [{fen, move_played, best_move, cp_loss, classification, theme?}]
  summary TEXT,
  played_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Re-reviews of the same game upsert instead of duplicating.
CREATE UNIQUE INDEX IF NOT EXISTS uq_coach_game_insights_user_ref_source
  ON coach_game_insights (user_id, game_ref, source);

-- Retrieval path: a student's most recent insights first.
CREATE INDEX IF NOT EXISTS idx_coach_game_insights_user_created
  ON coach_game_insights (user_id, created_at DESC);

-- Structured filter path: a student's games in a given opening.
CREATE INDEX IF NOT EXISTS idx_coach_game_insights_user_opening
  ON coach_game_insights (user_id, opening);

-- Service-key-only access: enable RLS with no permissive policies so the
-- anon/authenticated roles are denied by default and only the service role
-- (which bypasses RLS) can read/write. Mirrors 010_coach_memory.sql intent —
-- this is a backend-owned table never touched by the browser client.
ALTER TABLE coach_game_insights ENABLE ROW LEVEL SECURITY;
