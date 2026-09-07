-- 038: add email/name to organization_members
-- The admin roster (listOrgCeMembers) and the member access route select these
-- columns since Jul 4 (9099545), but they were never created in prod — every
-- select failed with 42703 and the admin panel silently rendered empty.
-- Nullable, no backfill here; online-member rows are backfilled from Clerk
-- out-of-band and written at registration going forward.

ALTER TABLE organization_members ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE organization_members ADD COLUMN IF NOT EXISTS name text;
