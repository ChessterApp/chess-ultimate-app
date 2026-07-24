-- Migration: Server-side pending branch-link registrations.
--
-- Branch-link durability fix (2026-07-24). The invite JWT alone was a fragile
-- carrier: Google OAuth drops Clerk `unsafeMetadata`, kids sign up with their
-- own Gmail (email fallback misses), and the 15-min JWT often expires before
-- sign-up even completes. This table persists the pending link server-side at
-- the moment the JWT is minted (AFTER branch-token validation passed), so
-- completion no longer depends on client storage or OAuth metadata.
--
-- Flow: verify route inserts a `pending` row keyed by the JWT's sha256
-- (`jti_hash`) AND sets an httpOnly `ce_pending_jti` cookie. The claim path /
-- server-side auto-claim looks the row up by hash, completes the link, and
-- flips the row to `claimed` (single-use). Rows expire after 7 days, checked
-- at read time — no cron needed.
--
-- Service-role only; no client access (RLS fail-closed, matching
-- 20260701_020_invite_jwts_consumed.sql).
--
-- Idempotent. Safe to re-run.

CREATE TABLE IF NOT EXISTS pending_registrations (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  jti_hash                  TEXT NOT NULL UNIQUE,
  student_id                TEXT NOT NULL,
  org_id                    UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  member_type               TEXT NOT NULL DEFAULT 'student'
    CHECK (member_type IN ('student', 'coach')),
  status                    TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'claimed', 'expired')),
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  claimed_by_clerk_user_id  TEXT,
  claimed_at                TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS pending_registrations_org_idx
  ON pending_registrations (org_id);

CREATE INDEX IF NOT EXISTS pending_registrations_created_at_idx
  ON pending_registrations (created_at);

-- ─── RLS ───────────────────────────────────────────────────────────────────
-- Writes + reads happen exclusively via the service role (verify route mints,
-- claim path completes). No client should ever query this table. Fail closed.

ALTER TABLE pending_registrations ENABLE ROW LEVEL SECURITY;

-- ─── link_attempts: allow the new pending-row success status ────────────────
-- The cookie→pending-row claim audits with `pending_row_success` to distinguish
-- it from the JWT-body path's `success`. CHECK constraints don't support
-- ADD IF NOT EXISTS, so drop + recreate with the extra value.

ALTER TABLE link_attempts
  DROP CONSTRAINT IF EXISTS link_attempts_status_check;

ALTER TABLE link_attempts
  ADD CONSTRAINT link_attempts_status_check
  CHECK (status IN (
    'success',
    'pending_row_success',
    'no_match',
    'multiple_match',
    'jwt_missing',
    'jwt_invalid',
    'jwt_expired',
    'jwt_replayed',
    'webhook_error'
  ));

-- ROLLBACK (commented):
-- ALTER TABLE link_attempts DROP CONSTRAINT IF EXISTS link_attempts_status_check;
-- ALTER TABLE link_attempts ADD CONSTRAINT link_attempts_status_check
--   CHECK (status IN ('success','no_match','multiple_match','jwt_missing',
--     'jwt_invalid','jwt_expired','jwt_replayed','webhook_error'));
-- DROP INDEX IF EXISTS pending_registrations_created_at_idx;
-- DROP INDEX IF EXISTS pending_registrations_org_idx;
-- DROP TABLE IF EXISTS pending_registrations;
