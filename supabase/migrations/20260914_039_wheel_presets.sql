-- ============================================================================
-- 20260914_039_wheel_presets.sql
-- Coach Prize Wheel (.ralphy/wheel-game-brief.md) — saved wheel configurations.
--
-- Backs the /games/wheel config editor: a coach can save multiple named wheels
-- (e.g. "младшая группа", "старшая группа"), switch between them and duplicate
-- one. Each preset stores its segments (label/color/emoji) as jsonb.
--
-- Security model (matches supabase/migrations/20260722_rls_lockdown_client_write.sql):
-- RLS enabled, direct client writes via the `authenticated` role. Any coach/admin
-- (authenticated) may READ all presets so they can share wheels across the school;
-- writes (INSERT/UPDATE/DELETE) are restricted to the preset owner via
-- created_by = public.clerk_uid() (Clerk user id = JWT `sub`, kept as TEXT).
--
-- Idempotent: safe to re-run (IF NOT EXISTS / DROP POLICY IF EXISTS).
-- ROLLBACK (manual): DROP TABLE IF EXISTS public.wheel_presets;
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS public.wheel_presets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  segments    JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_by  TEXT NOT NULL DEFAULT public.clerk_uid(),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS wheel_presets_created_by_idx
  ON public.wheel_presets (created_by);

ALTER TABLE public.wheel_presets ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.wheel_presets FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.wheel_presets TO authenticated;

-- Read: any authenticated coach/admin can see all presets (shared at the school).
DROP POLICY IF EXISTS wheel_presets_read ON public.wheel_presets;
CREATE POLICY wheel_presets_read
  ON public.wheel_presets
  FOR SELECT
  TO authenticated
  USING (true);

-- Write: only the owner may insert/update/delete their own presets.
DROP POLICY IF EXISTS wheel_presets_insert ON public.wheel_presets;
CREATE POLICY wheel_presets_insert
  ON public.wheel_presets
  FOR INSERT
  TO authenticated
  WITH CHECK (created_by = public.clerk_uid());

DROP POLICY IF EXISTS wheel_presets_update ON public.wheel_presets;
CREATE POLICY wheel_presets_update
  ON public.wheel_presets
  FOR UPDATE
  TO authenticated
  USING (created_by = public.clerk_uid())
  WITH CHECK (created_by = public.clerk_uid());

DROP POLICY IF EXISTS wheel_presets_delete ON public.wheel_presets;
CREATE POLICY wheel_presets_delete
  ON public.wheel_presets
  FOR DELETE
  TO authenticated
  USING (created_by = public.clerk_uid());

COMMIT;
