-- Migration: Single-use enforcement for invite-flow JWTs.
--
-- Phase 5 of the Chess Empire → Chesster onboarding arc. The Clerk
-- ``user.created`` webhook records the sha256 hex of each invite JWT it
-- consumes so a replayed webhook (or a leaked JWT) can never double-link a
-- student to an organization.
--
-- Only the hash lands in the DB — the raw JWT never touches Supabase, so a
-- compromised row cannot be used to forge future auth.
--
-- Retain rows for ~30 days for post-hoc audit; older rows may be pruned by
-- a housekeeping job. Service-role only; no client access (RLS matches the
-- style of 20260630_018_branch_invite_tokens.sql).
--
-- Idempotent. Safe to re-run.

CREATE TABLE IF NOT EXISTS invite_jwts_consumed (
  jti_hash             TEXT PRIMARY KEY,
  organization_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  branch_token_id      UUID NOT NULL REFERENCES branch_invite_tokens(id) ON DELETE CASCADE,
  external_student_id  TEXT NOT NULL,
  clerk_user_id        TEXT NOT NULL,
  consumed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS invite_jwts_consumed_org_idx
  ON invite_jwts_consumed (organization_id);

CREATE INDEX IF NOT EXISTS invite_jwts_consumed_consumed_at_idx
  ON invite_jwts_consumed (consumed_at);

-- ─── RLS ───────────────────────────────────────────────────────────────────
-- Consumption is service-role only (writes from the webhook handler); no
-- client should ever query this table directly. Fail closed.

ALTER TABLE invite_jwts_consumed ENABLE ROW LEVEL SECURITY;

-- ROLLBACK (commented):
-- DROP INDEX IF EXISTS invite_jwts_consumed_consumed_at_idx;
-- DROP INDEX IF EXISTS invite_jwts_consumed_org_idx;
-- DROP TABLE IF EXISTS invite_jwts_consumed;
