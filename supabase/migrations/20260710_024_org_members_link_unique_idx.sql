-- Migration: unique index backing the webhook member-link upsert.
--
-- The Clerk webhook (frontend/src/app/api/webhooks/clerk/route.ts) upserts
-- organization_members with
--   onConflict: 'organization_id,external_student_id,external_source'
-- but 20260704_021 never created a matching unique index, so Postgres
-- rejects every webhook link with "there is no unique or exclusion
-- constraint matching the ON CONFLICT specification". This index fixes
-- self-registration linking for all students.
--
-- NULL external_student_id rows (owners, unlinked members) never conflict:
-- Postgres treats NULLs as distinct in unique indexes.

CREATE UNIQUE INDEX IF NOT EXISTS organization_members_external_link_uidx
  ON organization_members (organization_id, external_student_id, external_source);

-- Rollback:
-- DROP INDEX IF EXISTS organization_members_external_link_uidx;
