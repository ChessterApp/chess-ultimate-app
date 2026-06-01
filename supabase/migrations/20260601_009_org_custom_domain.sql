-- Migration: Add custom_domain columns to organizations (paid white-label upgrade).
-- Source PRD: docs/prd/custom-domain-flow.md
-- Related ADR: docs/adr/0005-subdomain-per-tenant-multi-tenancy.md (Follow-ups)
--
-- Adds:
--   * organizations.custom_domain (TEXT, lowercased, no trailing dot, no protocol)
--   * organizations.custom_domain_status ('pending'|'verifying'|'active'|'failed')
--   * organizations.custom_domain_verified_at (TIMESTAMPTZ)
--   * organizations.custom_domain_vercel_id (TEXT — Vercel's domain identifier)
--   * Unique partial index on custom_domain (ignoring NULL)
--   * Status partial index for admin dashboards
--
-- The existing RLS policy `org_admin_update` on `organizations` already gates
-- writes by `is_org_role(... ['owner','admin'])`, so this column inherits the
-- correct tenancy enforcement with no new policy needed.
--
-- Idempotent: uses IF NOT EXISTS guards. Safe to re-run.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS custom_domain TEXT,
  ADD COLUMN IF NOT EXISTS custom_domain_status TEXT,
  ADD COLUMN IF NOT EXISTS custom_domain_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS custom_domain_vercel_id TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'organizations_custom_domain_status_check'
  ) THEN
    ALTER TABLE organizations
      ADD CONSTRAINT organizations_custom_domain_status_check
      CHECK (
        custom_domain_status IN ('pending','verifying','active','failed')
        OR custom_domain_status IS NULL
      );
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_org_custom_domain
  ON organizations (custom_domain)
  WHERE custom_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_org_custom_domain_status
  ON organizations (custom_domain_status)
  WHERE custom_domain_status IS NOT NULL;

-- ROLLBACK (commented; copy-paste to revert):
-- DROP INDEX IF EXISTS idx_org_custom_domain_status;
-- DROP INDEX IF EXISTS idx_org_custom_domain;
-- ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_custom_domain_status_check;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS custom_domain_vercel_id;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS custom_domain_verified_at;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS custom_domain_status;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS custom_domain;
