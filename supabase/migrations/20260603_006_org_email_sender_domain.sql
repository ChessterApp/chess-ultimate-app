-- Migration: Add email_sender_domain columns to organizations (Pro+ branded
-- email senders, PRD §11.2 #4 / Phase 2).
--
-- Naming mirrors the custom-domain column shape from migration 009:
--   * organizations.email_sender_domain         TEXT
--   * organizations.email_sender_status         TEXT  (pending|verifying|active|failed)
--   * organizations.email_sender_verified_at    TIMESTAMPTZ
--   * organizations.email_sender_resend_id      TEXT
--
-- Existing RLS policy `org_admin_update` on `organizations` already gates
-- writes by `is_org_role(... ['owner','admin'])`, so this column inherits
-- the correct tenancy enforcement with no new policy needed.
--
-- Idempotent: uses IF NOT EXISTS guards. Safe to re-run.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS email_sender_domain TEXT,
  ADD COLUMN IF NOT EXISTS email_sender_status TEXT,
  ADD COLUMN IF NOT EXISTS email_sender_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS email_sender_resend_id TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'organizations_email_sender_status_check'
  ) THEN
    ALTER TABLE organizations
      ADD CONSTRAINT organizations_email_sender_status_check
      CHECK (
        email_sender_status IN ('pending','verifying','active','failed')
        OR email_sender_status IS NULL
      );
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_org_email_sender_domain
  ON organizations (email_sender_domain)
  WHERE email_sender_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_org_email_sender_status
  ON organizations (email_sender_status)
  WHERE email_sender_status IS NOT NULL;

-- ROLLBACK (commented; copy-paste to revert):
-- DROP INDEX IF EXISTS idx_org_email_sender_status;
-- DROP INDEX IF EXISTS idx_org_email_sender_domain;
-- ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_email_sender_status_check;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS email_sender_resend_id;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS email_sender_verified_at;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS email_sender_status;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS email_sender_domain;
