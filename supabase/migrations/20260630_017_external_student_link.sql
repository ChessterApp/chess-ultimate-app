-- Migration: External-system student link on organization_members.
--
-- Phase 1 of the Chess Empire → Chesster onboarding arc (plan:
-- /root/.claude/plans/ancient-greeting-thimble.md). Each Chesster member row
-- can carry a logical pointer to a record in an external SIS — Chess Empire
-- being the first integration. A `UNIQUE` constraint enforces one Chesster
-- account per external student id within an org, race-safe at write time.
--
-- Designed to be extensible — `external_source` is a free-form TEXT so we can
-- add future schools without another migration.
--
-- RLS: no new policies; the existing `organization_members` policies cover
-- read/write access. Service-role writes (verify route + nightly cron)
-- bypass RLS by design.
--
-- Idempotent. Safe to re-run.

-- ─── Columns ───────────────────────────────────────────────────────────────

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS external_student_id UUID;

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS external_source TEXT DEFAULT 'chess_empire';

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_status TEXT
    CHECK (link_status IN ('pending', 'verified', 'frozen', 'revoked'));

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_verified_at TIMESTAMPTZ;

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS link_revoked_at TIMESTAMPTZ;

-- ─── Uniqueness ────────────────────────────────────────────────────────────
-- One external student per (org, source). Partial index so rows without an
-- external link (Chesster-native members) don't collide on (NULL, 'x').

CREATE UNIQUE INDEX IF NOT EXISTS idx_org_members_external_student_unique
  ON organization_members (organization_id, external_student_id, external_source)
  WHERE external_student_id IS NOT NULL;

-- ─── Admin-query index ─────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_org_members_external_source_status
  ON organization_members (organization_id, external_source, link_status)
  WHERE external_student_id IS NOT NULL;

-- ROLLBACK (commented):
-- DROP INDEX IF EXISTS idx_org_members_external_source_status;
-- DROP INDEX IF EXISTS idx_org_members_external_student_unique;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_revoked_at;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_verified_at;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS link_status;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS external_source;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS external_student_id;
