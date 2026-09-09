-- Migration 015: Best-of-N with engine selection (CL Phase 2, Slice 3).
--
-- For a position-anchored coach turn, the coach can generate several candidate
-- explanations, let the ENGINE rank the correctness channel (via the existing
-- engine_grounded extractor), and then let a cheap-tier LLM judge pick the
-- clearest among the engine-passing candidates only. The engine keeps
-- correctness honest; the judge is never allowed to promote an engine-failing
-- candidate. This table is the append-only audit ledger of that selection:
--
--   coach_bestofn_audit — one immutable row per best-of-N turn. Records how many
--     candidates were generated, each candidate's engine score + status and its
--     (truncated) text, the judge's choice + reason (or null when no judge ran),
--     the finally selected candidate, any fallback reason (null on a clean
--     selection), and the turn latency. The candidate text is stored as DATA,
--     truncated (<=2000 chars each) — never re-interpreted as instructions.
--
-- Selection uses engine verdicts + judge clarity ONLY — never user feedback or
-- ratings (feedback is never a reward). Gated entirely behind COACH_BESTOFN;
-- with the flag off nothing reads or writes here. Additive only; idempotent.

CREATE TABLE IF NOT EXISTS coach_bestofn_audit (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  session_id TEXT,
  fen TEXT,
  n INT NOT NULL,
  candidates JSONB NOT NULL,               -- [{idx, engine_score, engine_status, text_truncated}]
  judge JSONB,                             -- {choice, reason, model} or null
  selected_idx INT NOT NULL,
  fallback_reason TEXT,                    -- null on a clean selection
  latency_ms INT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Audit history per user, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_bestofn_audit_user_created
  ON coach_bestofn_audit (user_id, created_at DESC);


-- Service-key-only access: enable RLS with no permissive policies so the
-- anon/authenticated roles are denied by default and only the service role
-- (which bypasses RLS) can read/write. Mirrors 013/014 intent — this is a
-- backend-owned table never touched by the browser client.
ALTER TABLE coach_bestofn_audit ENABLE ROW LEVEL SECURITY;
