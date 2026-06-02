-- Migration: Add clerk_org_id column to organizations (Clerk Organizations wiring).
-- Source PRD: docs/prd/clerk-orgs-wiring.md (Phase 4 of the white-label arc)
--
-- Adds:
--   * organizations.clerk_org_id (TEXT, UNIQUE, nullable — backfilled per-org by
--     the super-admin sync endpoint or the org-create handler).
--   * Partial index for fast lookups during webhook idempotency checks.
--
-- The new column carries no tenant data — it is a metadata pointer at the org
-- row itself — so no RLS policy changes are required.
--
-- Idempotent: uses IF NOT EXISTS guards. Safe to re-run.
--
-- Applied to live Supabase project qtzujwiqzbgyhdgulvcd at: 2026-06-02

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS clerk_org_id TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'organizations_clerk_org_id_key'
  ) THEN
    ALTER TABLE organizations
      ADD CONSTRAINT organizations_clerk_org_id_key UNIQUE (clerk_org_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_organizations_clerk_org_id
  ON organizations (clerk_org_id)
  WHERE clerk_org_id IS NOT NULL;

-- ROLLBACK (commented; copy-paste to revert):
-- DROP INDEX IF EXISTS idx_organizations_clerk_org_id;
-- ALTER TABLE organizations DROP CONSTRAINT IF EXISTS organizations_clerk_org_id_key;
-- ALTER TABLE organizations DROP COLUMN IF EXISTS clerk_org_id;
