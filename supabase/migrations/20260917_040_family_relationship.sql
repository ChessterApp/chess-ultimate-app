-- Migration: family relationship label on organization_members.
--
-- Family Registration Phase 1. One Chesster account may hold MULTIPLE verified
-- Chess Empire student links ("family members"). This column labels each link so
-- the account owner's own record is distinguishable from guardian-managed ones:
--   'self'  = the account owner IS the student (default; every existing row).
--   'child' = a guardian-managed minor family member.
--   'other' = any other guardian-managed family member.
--
-- The table is small, so a plain CHECK (no NOT VALID / VALIDATE split) is fine.
-- Idempotent. Safe to re-run. NOT applied to any database by this change.

ALTER TABLE organization_members
  ADD COLUMN IF NOT EXISTS relationship TEXT NOT NULL DEFAULT 'self';

ALTER TABLE organization_members
  DROP CONSTRAINT IF EXISTS organization_members_relationship_check;

ALTER TABLE organization_members
  ADD CONSTRAINT organization_members_relationship_check
  CHECK (relationship IN ('self', 'child', 'other'));

COMMENT ON COLUMN organization_members.relationship IS
  'Family link type: ''self'' = the account owner is the student; ''child''/''other'' = a guardian-managed family member.';

-- Rollback:
-- ALTER TABLE organization_members DROP CONSTRAINT IF EXISTS organization_members_relationship_check;
-- ALTER TABLE organization_members DROP COLUMN IF EXISTS relationship;
