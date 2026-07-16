-- Migration: Track Vercel registration status for each org's *.chesster.io subdomain.
-- Source: docs/prd/PRD-self-serve-school-onboarding.md + cosmic-mixing-wall fix plan.
--
-- Adds:
--   * organizations.subdomain_status ('pending'|'verifying'|'active'|'failed')
--   * organizations.subdomain_verified_at (TIMESTAMPTZ)
--   * organizations.subdomain_vercel_id (TEXT)
--   * organizations.subdomain_last_error (TEXT)
--   * Partial index on subdomain_status for admin dashboards / backfill query
--
-- Idempotent.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS subdomain_status TEXT,
  ADD COLUMN IF NOT EXISTS subdomain_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS subdomain_vercel_id TEXT,
  ADD COLUMN IF NOT EXISTS subdomain_last_error TEXT;

ALTER TABLE organizations
  DROP CONSTRAINT IF EXISTS organizations_subdomain_status_check;

ALTER TABLE organizations
  ADD CONSTRAINT organizations_subdomain_status_check
  CHECK (subdomain_status IN ('pending','verifying','active','failed') OR subdomain_status IS NULL);

CREATE INDEX IF NOT EXISTS idx_org_subdomain_status
  ON organizations (subdomain_status) WHERE subdomain_status IS NOT NULL;
