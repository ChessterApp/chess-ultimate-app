-- Migration: Audit log for student verify attempts.
--
-- Phase 1 of the Chess Empire → Chesster onboarding arc. Every call to the
-- DOB-gate verify endpoint writes a row here: success or failure, with the
-- reason for failures. Used for (a) the documented rate-limit policy
-- (3/student/IP/hour, 10/IP/hour), and (b) the anomaly-alert path
-- (>20 failed attempts/day on a branch token → ping admin, auto-suspend).
--
-- `external_student_id` is NULLABLE — a no-match attempt (typo, made-up
-- name) won't have one. `reason` is a short code like 'wrong_dob',
-- 'inactive', 'branch_mismatch', 'already_registered', 'rate_limited'.
--
-- Idempotent. Safe to re-run.

CREATE TABLE IF NOT EXISTS student_verify_attempts (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  external_student_id  UUID,
  branch_token_id      UUID REFERENCES branch_invite_tokens(id) ON DELETE SET NULL,
  ip                   TEXT,
  success              BOOLEAN NOT NULL,
  reason               TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_verify_attempts_student_time
  ON student_verify_attempts (external_student_id, created_at)
  WHERE external_student_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_verify_attempts_ip_time
  ON student_verify_attempts (ip, created_at);

-- ─── RLS ───────────────────────────────────────────────────────────────────
-- Writes happen via service role. Reads restricted to org admins for the
-- audit-log view in the admin panel.

ALTER TABLE student_verify_attempts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS verify_attempts_org_admin_read ON student_verify_attempts;
CREATE POLICY verify_attempts_org_admin_read ON student_verify_attempts
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = student_verify_attempts.organization_id
      AND om.user_id = auth.uid()::text
      AND om.role IN ('owner', 'admin')
    )
  );

-- ROLLBACK (commented):
-- DROP POLICY IF EXISTS verify_attempts_org_admin_read ON student_verify_attempts;
-- DROP INDEX IF EXISTS idx_verify_attempts_ip_time;
-- DROP INDEX IF EXISTS idx_verify_attempts_student_time;
-- DROP TABLE IF EXISTS student_verify_attempts;
