-- Migration 014: Automatic curriculum (CL Phase 2, Slice 2 — engine-measured
-- learnability).
--
-- A per-student training curriculum, DERIVED offline from engine-verified data
-- (never computed on a chat turn):
--
--   coach_curriculum       — the live curriculum. Exactly ONE current row per
--     user (UNIQUE (user_id), upserted by the offline builder). `focus` is an
--     array of <=3 target themes, each keyed on engine-measured learnability:
--     a high-blunder theme at a difficulty near the student's ~50% solve-rate
--     frontier (maximally learnable — not too easy, not too hard). This is
--     DERIVED state — the audit ledger below is the source of truth.
--
--   coach_curriculum_audit — immutable, append-only ledger. Every recompute
--     writes one row capturing the chosen focus and the inputs summary that
--     justified it (counts + time window used).
--
-- Learnability comes ONLY from engine-verified blunders (coach_game_insights)
-- and objective solve outcomes (puzzle_attempts) — never from user feedback or
-- ratings (feedback is never a reward). Gated entirely behind COACH_CURRICULUM;
-- with the flag off nothing reads or writes here. Additive only; idempotent.

CREATE TABLE IF NOT EXISTS coach_curriculum (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  focus JSONB NOT NULL,                    -- [{theme, score, blunder_count, avg_cp_loss, solve_rate, target_difficulty, rationale}] (<=3)
  computed_from JSONB,                     -- {games, blunders, attempts, since, ...} inputs summary
  valid_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Exactly one current curriculum row per user; the offline builder upserts on
-- this key. History lives in coach_curriculum_audit, not here.
CREATE UNIQUE INDEX IF NOT EXISTS uq_coach_curriculum_user
  ON coach_curriculum (user_id);


CREATE TABLE IF NOT EXISTS coach_curriculum_audit (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  focus JSONB NOT NULL,
  computed_from JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Audit history per user, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_curriculum_audit_user_created
  ON coach_curriculum_audit (user_id, created_at DESC);


-- Service-key-only access: enable RLS with no permissive policies so the
-- anon/authenticated roles are denied by default and only the service role
-- (which bypasses RLS) can read/write. Mirrors 013_coach_playbook.sql intent —
-- these are backend-owned tables never touched by the browser client.
ALTER TABLE coach_curriculum ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_curriculum_audit ENABLE ROW LEVEL SECURITY;
