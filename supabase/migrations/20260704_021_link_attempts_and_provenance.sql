-- Migration: link_attempts audit table + provenance on organization_members.
--
-- Phase 1 of the "robust email → Chess Empire student linking" arc (plan:
-- /root/.claude/plans/melodic-noodling-micali.md). Backs the webhook
-- hardening, email auto-match, admin backfill queue, and orphan-observability
-- surface. All rows must be reachable via existing (or new) org-admin
-- policies; no client should ever be able to read another org's attempts.
--
-- Idempotent. Safe to re-run.
--
-- Dependency note: `invite_jwts_consumed` from 20260701_020 was never applied
-- to prod. This migration re-creates it (IF NOT EXISTS) so the webhook can
-- rely on it without ordering surprises.

-- ─── 1. invite_jwts_consumed (idempotent guard, applied here if 020 missed prod) ──

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

ALTER TABLE invite_jwts_consumed ENABLE ROW LEVEL SECURITY;

-- ─── 2. organization_members provenance columns ───────────────────────────

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_source TEXT
    CHECK (link_source IN ('jwt', 'email_auto', 'admin_manual', 'backfill'));

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_approved_by TEXT;

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_notes TEXT;

-- Loosen the link_status check to add `pending_confirm` (email auto-match).
-- Drop then recreate — CHECK constraints don't support ADD IF NOT EXISTS.

ALTER TABLE organization_members
  DROP CONSTRAINT IF EXISTS organization_members_link_status_check;

ALTER TABLE organization_members
  ADD CONSTRAINT organization_members_link_status_check
  CHECK (link_status IS NULL OR link_status IN (
    'pending',
    'pending_confirm',
    'verified',
    'frozen',
    'revoked'
  ));

-- ─── 3. link_attempts audit table ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS link_attempts (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id       UUID REFERENCES organizations(id) ON DELETE CASCADE,
  user_id               TEXT,
  email                 TEXT,
  attempted_source      TEXT NOT NULL
    CHECK (attempted_source IN (
      'jwt',
      'email_auto',
      'admin_manual',
      'backfill'
    )),
  status                TEXT NOT NULL
    CHECK (status IN (
      'success',
      'no_match',
      'multiple_match',
      'jwt_missing',
      'jwt_invalid',
      'jwt_expired',
      'jwt_replayed',
      'webhook_error'
    )),
  candidate_student_ids UUID[],
  chosen_student_id     UUID,
  error_message         TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS link_attempts_org_status_created_idx
  ON link_attempts (organization_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS link_attempts_user_idx
  ON link_attempts (user_id)
  WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS link_attempts_email_idx
  ON link_attempts (lower(email))
  WHERE email IS NOT NULL;

-- ─── 4. RLS ───────────────────────────────────────────────────────────────
-- link_attempts: org admins can read their own org's attempts. Writes are
-- service-role only (webhook + admin endpoint). The is_org_role() helper
-- already exists (see 20260601_008_rls_hardening.sql).

ALTER TABLE link_attempts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "link_attempts_admin_read" ON link_attempts;
CREATE POLICY "link_attempts_admin_read" ON link_attempts
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND is_org_role(organization_id, ARRAY['owner', 'admin'])
  );

-- ─── 5. Self-read policy on organization_members ──────────────────────────
-- The existing `org_members_read` policy scopes reads to any member of the
-- org via `is_org_member(...)`. That is intentional (admin queries + CE
-- admin panel). The plan calls for an explicit self-read fallback so a user
-- can `select` their own linkage even if `is_org_member` short-circuits.
-- Additive policy; both are ORed at query time.

DROP POLICY IF EXISTS "org_members_read_self" ON organization_members;
CREATE POLICY "org_members_read_self" ON organization_members
  FOR SELECT
  USING (user_id = (auth.uid())::text);

-- ROLLBACK (commented):
-- DROP POLICY IF EXISTS "org_members_read_self" ON organization_members;
-- DROP POLICY IF EXISTS "link_attempts_admin_read" ON link_attempts;
-- DROP INDEX IF EXISTS link_attempts_email_idx;
-- DROP INDEX IF EXISTS link_attempts_user_idx;
-- DROP INDEX IF EXISTS link_attempts_org_status_created_idx;
-- DROP TABLE IF EXISTS link_attempts;
-- ALTER TABLE organization_members DROP CONSTRAINT IF EXISTS organization_members_link_status_check;
-- ALTER TABLE organization_members ADD CONSTRAINT organization_members_link_status_check
--   CHECK (link_status IN ('pending', 'verified', 'frozen', 'revoked'));
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_notes;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_approved_by;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_source;
