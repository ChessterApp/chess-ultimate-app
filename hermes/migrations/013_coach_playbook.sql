-- Migration 013: Engine-verified coaching playbook (CL Phase 2, Slice 1).
--
-- The ACE loop (Generator → Reflector → Curator) distills recurring coaching
-- patterns from real transcripts into short, reusable, engine-verified entries
-- that are injected into the system prompt. Two additive tables:
--
--   coach_playbook       — the live playbook. Each row is one distilled pattern
--     (title, theme, tags, advice, optional worked example). `verified` is true
--     only when the engine adjudicated its concrete move/eval claims and none
--     were refuted; unverifiable entries survive on Reflector confidence alone
--     and stay verified=false so injection can prefer verified ones. This is
--     DERIVED state — the audit ledger below is the source of truth.
--
--   coach_playbook_audit — immutable, append-only ledger. Every accept / reject
--     / merge / retire writes one row with the source turn ids and the engine
--     verdict that justified the decision.
--
-- Gated entirely behind COACH_PLAYBOOK; with the flag off nothing reads or
-- writes here. Additive only; idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS coach_playbook (
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  theme TEXT NOT NULL,                     -- opening / tactic / endgame / habit / ...
  tags TEXT[],
  advice TEXT NOT NULL,
  example_fen TEXT,
  example_line TEXT,
  verified BOOLEAN NOT NULL DEFAULT false,
  engine_evidence JSONB,
  source_turn_ids TEXT[],
  status TEXT NOT NULL CHECK (status IN ('active', 'retired', 'rejected')) DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Injection read path: active entries filtered/ranked by theme.
CREATE INDEX IF NOT EXISTS idx_coach_playbook_status_theme
  ON coach_playbook (status, theme);

-- Prefer engine-verified entries.
CREATE INDEX IF NOT EXISTS idx_coach_playbook_verified
  ON coach_playbook (verified);


CREATE TABLE IF NOT EXISTS coach_playbook_audit (
  id BIGSERIAL PRIMARY KEY,
  playbook_id BIGINT,
  action TEXT NOT NULL CHECK (action IN ('accept', 'reject', 'merge', 'retire')),
  detail JSONB NOT NULL,
  engine_verdict TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Audit history per playbook entry, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_playbook_audit_playbook_created
  ON coach_playbook_audit (playbook_id, created_at DESC);


-- Service-key-only access: enable RLS with no permissive policies so the
-- anon/authenticated roles are denied by default and only the service role
-- (which bypasses RLS) can read/write. Mirrors 010_coach_memory.sql intent —
-- these are backend-owned tables never touched by the browser client.
ALTER TABLE coach_playbook ENABLE ROW LEVEL SECURITY;
ALTER TABLE coach_playbook_audit ENABLE ROW LEVEL SECURITY;
