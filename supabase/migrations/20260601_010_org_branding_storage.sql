-- Migration: Org branding storage bucket + RLS policies (per-org branding completion).
-- Source PRD: docs/prd/per-org-branding-completion.md (Deliverable 1)
--
-- Creates the `org-branding` Supabase Storage bucket so that owners/admins can
-- upload logo + favicon files for their org. Object keys are organised under
-- `org-branding/<org_uuid>/<kind>.<ext>` so the org_id is the first path
-- segment — RLS policies use this to gate writes by membership/role.
--
-- Public read so anonymous visitors can fetch logos/favicons.
--
-- Idempotent: uses INSERT … ON CONFLICT DO NOTHING for the bucket row and
-- `DROP POLICY IF EXISTS … CREATE POLICY …` for the policies. Safe to re-run.
--
-- Notes:
--   * `storage.objects` RLS is already enabled by Supabase's storage extension;
--     we only define policies here.
--   * `(storage.foldername(name))[1]` returns the first path segment of the
--     object's `name` column (e.g. for `org-branding/<uuid>/logo.png` ->
--     `<uuid>`). We cast to uuid and feed to the existing `is_org_role`
--     helper from migration 008.

-- ============================================================================
-- A. Bucket row
-- ============================================================================

INSERT INTO storage.buckets (id, name, public)
VALUES ('org-branding', 'org-branding', true)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- B. RLS policies on storage.objects scoped to the org-branding bucket
-- ============================================================================

-- Public read: logos/favicons served to anonymous visitors.
DROP POLICY IF EXISTS "org_branding_public_read" ON storage.objects;
CREATE POLICY "org_branding_public_read" ON storage.objects
  FOR SELECT
  USING (bucket_id = 'org-branding');

-- Insert: only org owners/admins of the org whose UUID is the first path
-- segment may upload. The CASE guard returns NULL (→ false in USING/WITH
-- CHECK) for malformed keys so a non-uuid segment can't crash the cast.
DROP POLICY IF EXISTS "org_branding_admin_insert" ON storage.objects;
CREATE POLICY "org_branding_admin_insert" ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'org-branding'
    AND is_org_role(
      CASE
        WHEN (storage.foldername(name))[1] ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN ((storage.foldername(name))[1])::uuid
        ELSE NULL
      END,
      ARRAY['owner', 'admin']
    )
  );

DROP POLICY IF EXISTS "org_branding_admin_update" ON storage.objects;
CREATE POLICY "org_branding_admin_update" ON storage.objects
  FOR UPDATE
  USING (
    bucket_id = 'org-branding'
    AND is_org_role(
      CASE
        WHEN (storage.foldername(name))[1] ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN ((storage.foldername(name))[1])::uuid
        ELSE NULL
      END,
      ARRAY['owner', 'admin']
    )
  );

DROP POLICY IF EXISTS "org_branding_admin_delete" ON storage.objects;
CREATE POLICY "org_branding_admin_delete" ON storage.objects
  FOR DELETE
  USING (
    bucket_id = 'org-branding'
    AND is_org_role(
      CASE
        WHEN (storage.foldername(name))[1] ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        THEN ((storage.foldername(name))[1])::uuid
        ELSE NULL
      END,
      ARRAY['owner', 'admin']
    )
  );

-- ============================================================================
-- ROLLBACK (commented; copy-paste to revert):
-- ============================================================================
-- DROP POLICY IF EXISTS "org_branding_admin_delete" ON storage.objects;
-- DROP POLICY IF EXISTS "org_branding_admin_update" ON storage.objects;
-- DROP POLICY IF EXISTS "org_branding_admin_insert" ON storage.objects;
-- DROP POLICY IF EXISTS "org_branding_public_read" ON storage.objects;
-- DELETE FROM storage.objects WHERE bucket_id = 'org-branding';
-- DELETE FROM storage.buckets WHERE id = 'org-branding';
