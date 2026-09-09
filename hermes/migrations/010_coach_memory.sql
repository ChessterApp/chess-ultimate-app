-- Migration 010: Per-student coach memory (CL Phase 1, Slice 1).
--
-- Two additive tables backing the memory writer + failure memory:
--
--   coach_memory_audit  — immutable, append-only ledger. Every memory mutation
--     (a profile update or a recorded correction) writes one row here with the
--     source_turn_id that caused it. The live profile (user_profiles) is DERIVED
--     state; this audit trail is the source of truth and is never mutated.
--
--   coach_corrections   — Reflexion-lite failure memory. When the turn's engine
--     verification flags a COACH-claimed illegal move (or refuted eval), one row
--     records the FEN, the claim, the engine verdict, and a one-line reflection.
--     The most recent active rows are injected into the system prompt so the
--     coach avoids repeating the same verified mistake.
--
-- Gated entirely behind COACH_MEMORY_WRITER; with the flag off nothing writes
-- here. Additive only; idempotent (safe to re-run). user_profiles needs no
-- change — its goals/weaknesses/style columns already exist.

CREATE TABLE IF NOT EXISTS coach_memory_audit (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('profile_update', 'correction')),
  content JSONB NOT NULL,
  source_turn_id TEXT,
  model TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-user audit history, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_memory_audit_user_created
  ON coach_memory_audit (user_id, created_at DESC);

-- Filter/aggregate by mutation kind.
CREATE INDEX IF NOT EXISTS idx_coach_memory_audit_kind
  ON coach_memory_audit (kind);


CREATE TABLE IF NOT EXISTS coach_corrections (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  turn_id TEXT,
  fen TEXT,
  claimed TEXT NOT NULL,
  engine_verdict TEXT NOT NULL,
  reflection TEXT NOT NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Prompt-injection read path: most-recent active corrections per user.
CREATE INDEX IF NOT EXISTS idx_coach_corrections_user_active_created
  ON coach_corrections (user_id, active, created_at DESC);


-- Service-key-only access: enable RLS with no permissive policies so the
-- anon/authenticated roles are denied by default and only the service role
-- (which bypasses RLS) can read/write. Mirrors 009_coach_feedback.sql intent —
-- these are backend-owned tables never touched by the browser client.
ALTER TABLE coach_memory_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_corrections ENABLE ROW LEVEL SECURITY;
