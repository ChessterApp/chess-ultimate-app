-- Migration: allow 'coach' in the organization_members role check.
--
-- The coach registration flow (frontend/src/lib/chess-empire-jwt-link.ts)
-- upserts organization_members with role='coach', but the check constraint
-- from 20260428_001 only allows ('owner', 'admin', 'teacher', 'student').
-- Every coach link therefore failed with
--   new row violates check constraint "organization_members_role_check"
-- leaving the member row missing and the homepage stuck in no_link state.

ALTER TABLE organization_members
  DROP CONSTRAINT organization_members_role_check;

ALTER TABLE organization_members
  ADD CONSTRAINT organization_members_role_check
  CHECK (role IN ('owner', 'admin', 'teacher', 'student', 'coach'));

-- Rollback:
-- ALTER TABLE organization_members DROP CONSTRAINT organization_members_role_check;
-- ALTER TABLE organization_members ADD CONSTRAINT organization_members_role_check
--   CHECK (role IN ('owner', 'admin', 'teacher', 'student'));
