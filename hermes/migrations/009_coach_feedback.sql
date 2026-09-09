-- Migration 009: Explicit user feedback on coach answers (👍/👎)
-- One verdict per user per turn — the explicit signal that complements the
-- implicit telemetry in coach_events (migration 007). LOG-ONLY: this table is
-- a training/analysis signal and is NEVER read in the serving path, never
-- alters prompts, routing, memory, or rewards (raw thumbs are not a reward —
-- sycophancy guard). Additive only; idempotent.

CREATE TABLE IF NOT EXISTS coach_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  session_id TEXT,
  turn_id TEXT NOT NULL,
  rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
  comment TEXT,
  surface TEXT NOT NULL DEFAULT 'text',     -- text | voice | review
  client_ts TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One verdict per user per turn — the UPSERT conflict target (a re-vote on the
-- same turn overwrites the prior rating; a retraction deletes the row).
CREATE UNIQUE INDEX IF NOT EXISTS uq_coach_feedback_user_turn
  ON coach_feedback (user_id, turn_id);

-- Join a verdict back to the turn's coach_events / coach_messages by turn_id.
CREATE INDEX IF NOT EXISTS idx_coach_feedback_turn
  ON coach_feedback (turn_id);

-- Per-user feedback history, most-recent first.
CREATE INDEX IF NOT EXISTS idx_coach_feedback_user_created
  ON coach_feedback (user_id, created_at);
