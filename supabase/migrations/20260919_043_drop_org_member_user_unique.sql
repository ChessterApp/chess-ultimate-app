-- Migration: drop the (organization_id, user_id) unique constraint on
-- organization_members.
--
-- Family Registration (universal add). A member row is keyed on the PARENT's
-- Clerk `user_id`, and the legacy unique constraint
-- `organization_members_organization_id_user_id_key = UNIQUE(organization_id, user_id)`
-- caps a single Chesster account at ONE member row per org. That makes adding a
-- SECOND family member (a real second child, same account, same branch) throw a
-- unique violation (500). This is the primary gate on the "one account → many
-- family members" flow.
--
-- Dropping it lets one account own multiple member rows in the same org (one per
-- external student). The anti-hijack invariant is UNCHANGED: the
-- `(organization_id, external_student_id, external_source)` unique index still
-- caps ONE member row per external student per org, so a self-registered student
-- can never get a second member row minted under a parent. Member upserts key on
-- that external-student index (see upsertMemberLink onConflict), never on
-- (organization_id, user_id) — verified by grep: no upsert uses
-- onConflict 'organization_id,user_id'.
--
-- STAGED ONLY: this file is NOT applied to any database by this change and there
-- is no deploy. Apply manually after review.
--
-- Idempotent (IF EXISTS). Safe to re-run.

ALTER TABLE organization_members
  DROP CONSTRAINT IF EXISTS organization_members_organization_id_user_id_key;

-- Rollback (re-add the cap; only safe once no account owns >1 row per org):
--   ALTER TABLE organization_members
--     ADD CONSTRAINT organization_members_organization_id_user_id_key
--     UNIQUE (organization_id, user_id);
