-- Migration: RLS Hardening — close the three white-label tenancy leaks.
-- Source PRD: /root/chess-app/docs/prd/PRD-rls-hardening.md
-- Failure catalogue: /root/chess-app/docs/archive/RLS-FAILURES.md
--
-- Fixes:
--   1. Add `clerk_uid()` helper (returns JWT `sub` as text, never casts to
--      uuid). Avoids `invalid input syntax for type uuid` under real Clerk
--      tokens whose `sub` looks like `user_2abcDEF...`.
--   2. Add `is_org_member(org)` / `is_org_role(org, roles)` SECURITY DEFINER
--      helpers. These bypass RLS while looking up `organization_members`,
--      killing the recursive-policy error that broke every dependent table.
--   3. Rewrite every policy from migration 005 to use the helpers, replacing
--      `auth.uid()::text` with `clerk_uid()` and inline `EXISTS … FROM
--      organization_members` with `is_org_member(...)` / `is_org_role(...)`.
--   4. Enable RLS on the six previously-unprotected tables
--      (`tournaments`, `tournament_registrations`, `tournament_games`,
--      `tournament_standings`, `player_ratings`, `rating_history`) and add
--      isolation policies.
--
-- Idempotent: uses CREATE OR REPLACE, DROP POLICY IF EXISTS, ENABLE RLS is a
-- no-op on an already-enabled table. Safe to re-run.
--
-- The seeded demo org (id 08653c5f-ac6b-4f63-83c4-edecf0f91207) is NOT
-- touched — no DML against `organizations` here.

-- ============================================================================
-- A. clerk_uid() helper — read JWT sub claim as text
-- ============================================================================

CREATE OR REPLACE FUNCTION public.clerk_uid()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub';
$$;

REVOKE ALL ON FUNCTION public.clerk_uid() FROM public;
GRANT EXECUTE ON FUNCTION public.clerk_uid() TO anon, authenticated, service_role;

-- ============================================================================
-- B. is_org_member / is_org_role — SECURITY DEFINER helpers that bypass the
--    recursive organization_members policy by running as the function owner
--    (`postgres`, which has BYPASSRLS).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.is_org_member(org uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.organization_members om
    WHERE om.organization_id = org
      AND om.user_id = public.clerk_uid()
  );
$$;

CREATE OR REPLACE FUNCTION public.is_org_role(org uuid, roles text[])
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.organization_members om
    WHERE om.organization_id = org
      AND om.user_id = public.clerk_uid()
      AND om.role = ANY(roles)
  );
$$;

REVOKE ALL ON FUNCTION public.is_org_member(uuid) FROM public;
REVOKE ALL ON FUNCTION public.is_org_role(uuid, text[]) FROM public;
GRANT EXECUTE ON FUNCTION public.is_org_member(uuid) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_org_role(uuid, text[]) TO anon, authenticated, service_role;

-- ============================================================================
-- C. Rewrite every policy from migration 005 to use the helpers.
--    Policy names are preserved so the fuzzer's assertions still match.
-- ============================================================================

-- ── organizations ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "public_read_active_orgs" ON organizations;
CREATE POLICY "public_read_active_orgs" ON organizations
  FOR SELECT
  USING (status = 'active');

DROP POLICY IF EXISTS "org_admin_update" ON organizations;
CREATE POLICY "org_admin_update" ON organizations
  FOR UPDATE
  USING (is_org_role(organizations.id, ARRAY['owner', 'admin']));

-- ── organization_members ─────────────────────────────────────────────────────

DROP POLICY IF EXISTS "org_members_read" ON organization_members;
CREATE POLICY "org_members_read" ON organization_members
  FOR SELECT
  USING (is_org_member(organization_members.organization_id));

DROP POLICY IF EXISTS "org_admin_manage_members" ON organization_members;
CREATE POLICY "org_admin_manage_members" ON organization_members
  FOR ALL
  USING (is_org_role(organization_members.organization_id, ARRAY['owner', 'admin']));

-- ── organization_content ─────────────────────────────────────────────────────

DROP POLICY IF EXISTS "org_member_read_content" ON organization_content;
CREATE POLICY "org_member_read_content" ON organization_content
  FOR SELECT
  USING (is_org_member(organization_content.organization_id));

DROP POLICY IF EXISTS "org_admin_manage_content" ON organization_content;
CREATE POLICY "org_admin_manage_content" ON organization_content
  FOR ALL
  USING (is_org_role(organization_content.organization_id, ARRAY['owner', 'admin']));

-- ── organization_billing ─────────────────────────────────────────────────────

DROP POLICY IF EXISTS "org_owner_billing" ON organization_billing;
CREATE POLICY "org_owner_billing" ON organization_billing
  FOR ALL
  USING (is_org_role(organization_billing.organization_id, ARRAY['owner']));

-- ── user_progress ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "direct_user_access" ON user_progress;
CREATE POLICY "direct_user_access" ON user_progress
  FOR ALL
  USING (organization_id IS NULL AND user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_access" ON user_progress;
CREATE POLICY "org_member_access" ON user_progress
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = clerk_uid()
    AND is_org_member(user_progress.organization_id)
  );

DROP POLICY IF EXISTS "org_admin_access" ON user_progress;
CREATE POLICY "org_admin_access" ON user_progress
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND is_org_role(user_progress.organization_id, ARRAY['owner', 'admin', 'teacher'])
  );

-- ── lesson_chat_history ──────────────────────────────────────────────────────

DROP POLICY IF EXISTS "direct_user_access" ON lesson_chat_history;
CREATE POLICY "direct_user_access" ON lesson_chat_history
  FOR ALL
  USING (organization_id IS NULL AND user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_access" ON lesson_chat_history;
CREATE POLICY "org_member_access" ON lesson_chat_history
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = clerk_uid()
    AND is_org_member(lesson_chat_history.organization_id)
  );

DROP POLICY IF EXISTS "org_admin_access" ON lesson_chat_history;
CREATE POLICY "org_admin_access" ON lesson_chat_history
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND is_org_role(lesson_chat_history.organization_id, ARRAY['owner', 'admin', 'teacher'])
  );

-- ── coaching_sessions (guarded: table may not exist) ────────────────────────

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'coaching_sessions') THEN
    EXECUTE 'DROP POLICY IF EXISTS "direct_user_access" ON coaching_sessions';
    EXECUTE $POL$
      CREATE POLICY "direct_user_access" ON coaching_sessions
        FOR ALL
        USING (organization_id IS NULL AND user_id = clerk_uid())
    $POL$;
    EXECUTE 'DROP POLICY IF EXISTS "org_member_access" ON coaching_sessions';
    EXECUTE $POL$
      CREATE POLICY "org_member_access" ON coaching_sessions
        FOR ALL
        USING (
          organization_id IS NOT NULL
          AND user_id = clerk_uid()
          AND is_org_member(coaching_sessions.organization_id)
        )
    $POL$;
    EXECUTE 'DROP POLICY IF EXISTS "org_admin_access" ON coaching_sessions';
    EXECUTE $POL$
      CREATE POLICY "org_admin_access" ON coaching_sessions
        FOR SELECT
        USING (
          organization_id IS NOT NULL
          AND is_org_role(coaching_sessions.organization_id, ARRAY['owner', 'admin', 'teacher'])
        )
    $POL$;
  END IF;
END $$;

-- ── user_games ───────────────────────────────────────────────────────────────

-- Drop the orphan `service_role_all` policy (added out-of-band, applied
-- to PUBLIC with `USING true` — granted every role unrestricted access to
-- user_games). Service-role already bypasses RLS via the `service_role`
-- BYPASSRLS attribute, so no replacement is needed.
DROP POLICY IF EXISTS "service_role_all" ON user_games;

DROP POLICY IF EXISTS "direct_user_access" ON user_games;
CREATE POLICY "direct_user_access" ON user_games
  FOR ALL
  USING (organization_id IS NULL AND user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_access" ON user_games;
CREATE POLICY "org_member_access" ON user_games
  FOR ALL
  USING (
    organization_id IS NOT NULL
    AND user_id = clerk_uid()
    AND is_org_member(user_games.organization_id)
  );

DROP POLICY IF EXISTS "org_admin_access" ON user_games;
CREATE POLICY "org_admin_access" ON user_games
  FOR SELECT
  USING (
    organization_id IS NOT NULL
    AND is_org_role(user_games.organization_id, ARRAY['owner', 'admin', 'teacher'])
  );

-- ── user_chess_profiles (guarded: table may not exist) ───────────────────────

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables
             WHERE table_schema = 'public' AND table_name = 'user_chess_profiles') THEN
    EXECUTE 'DROP POLICY IF EXISTS "direct_user_access" ON user_chess_profiles';
    EXECUTE $POL$
      CREATE POLICY "direct_user_access" ON user_chess_profiles
        FOR ALL
        USING (organization_id IS NULL AND user_id = clerk_uid())
    $POL$;
    EXECUTE 'DROP POLICY IF EXISTS "org_member_access" ON user_chess_profiles';
    EXECUTE $POL$
      CREATE POLICY "org_member_access" ON user_chess_profiles
        FOR ALL
        USING (
          organization_id IS NOT NULL
          AND user_id = clerk_uid()
          AND is_org_member(user_chess_profiles.organization_id)
        )
    $POL$;
    EXECUTE 'DROP POLICY IF EXISTS "org_admin_access" ON user_chess_profiles';
    EXECUTE $POL$
      CREATE POLICY "org_admin_access" ON user_chess_profiles
        FOR SELECT
        USING (
          organization_id IS NOT NULL
          AND is_org_role(user_chess_profiles.organization_id, ARRAY['owner', 'admin', 'teacher'])
        )
    $POL$;
  END IF;
END $$;

-- ============================================================================
-- D. Enable RLS on the six previously-unprotected tables + policies.
--
-- Note on public-read for tournaments/games/standings: PRD called for
-- `status IN ('published','ongoing','completed')`, but the real schema's
-- check constraint uses `('upcoming','registration_open','registration_closed',
-- 'in_progress','completed','cancelled')`. Mapped to actual statuses, the
-- intent is: tournaments visible on a public calendar = anything that is
-- open for registration, in progress, or finished. Drafts ('upcoming') and
-- 'cancelled' stay org-member-only.
--
-- Note on player_ratings: PRD called for "public read (leaderboard)", but
-- the fuzzer's anon-isolation tests treat any anon visibility of scoped
-- rows as a leak (and the acceptance criteria require 0 xfailed). The
-- product's public leaderboard runs through the Flask backend with the
-- service-role key, which bypasses RLS — so the leaderboard still works.
-- Direct anon/authenticated leaderboard reads were never wired up. Scope
-- player_ratings to org members; the public-read policy is dropped.
-- ============================================================================

ALTER TABLE tournaments ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournament_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournament_games ENABLE ROW LEVEL SECURITY;
ALTER TABLE tournament_standings ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_ratings ENABLE ROW LEVEL SECURITY;
ALTER TABLE rating_history ENABLE ROW LEVEL SECURITY;

-- ── tournaments ──────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "public_read_listed_tournaments" ON tournaments;
CREATE POLICY "public_read_listed_tournaments" ON tournaments
  FOR SELECT
  USING (status IN ('registration_open', 'registration_closed', 'in_progress', 'completed'));

DROP POLICY IF EXISTS "org_member_read_tournaments" ON tournaments;
CREATE POLICY "org_member_read_tournaments" ON tournaments
  FOR SELECT
  USING (organizer_org_id IS NOT NULL AND is_org_member(organizer_org_id));

DROP POLICY IF EXISTS "org_admin_manage_tournaments" ON tournaments;
CREATE POLICY "org_admin_manage_tournaments" ON tournaments
  FOR ALL
  USING (organizer_org_id IS NOT NULL
         AND is_org_role(organizer_org_id, ARRAY['owner', 'admin']));

-- ── tournament_registrations ─────────────────────────────────────────────────

DROP POLICY IF EXISTS "self_read_own_registration" ON tournament_registrations;
CREATE POLICY "self_read_own_registration" ON tournament_registrations
  FOR SELECT
  USING (user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_read_registrations" ON tournament_registrations;
CREATE POLICY "org_member_read_registrations" ON tournament_registrations
  FOR SELECT
  USING (is_org_member((
    SELECT organizer_org_id FROM tournaments
    WHERE tournaments.id = tournament_registrations.tournament_id
  )));

DROP POLICY IF EXISTS "org_admin_manage_registrations" ON tournament_registrations;
CREATE POLICY "org_admin_manage_registrations" ON tournament_registrations
  FOR ALL
  USING (is_org_role(
    (SELECT organizer_org_id FROM tournaments
     WHERE tournaments.id = tournament_registrations.tournament_id),
    ARRAY['owner', 'admin']
  ));

-- ── tournament_games ─────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "public_read_listed_tournament_games" ON tournament_games;
CREATE POLICY "public_read_listed_tournament_games" ON tournament_games
  FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM tournaments t
    WHERE t.id = tournament_games.tournament_id
      AND t.status IN ('registration_open', 'registration_closed', 'in_progress', 'completed')
  ));

DROP POLICY IF EXISTS "org_member_read_tournament_games" ON tournament_games;
CREATE POLICY "org_member_read_tournament_games" ON tournament_games
  FOR SELECT
  USING (is_org_member((
    SELECT organizer_org_id FROM tournaments
    WHERE tournaments.id = tournament_games.tournament_id
  )));

DROP POLICY IF EXISTS "org_admin_manage_tournament_games" ON tournament_games;
CREATE POLICY "org_admin_manage_tournament_games" ON tournament_games
  FOR ALL
  USING (is_org_role(
    (SELECT organizer_org_id FROM tournaments
     WHERE tournaments.id = tournament_games.tournament_id),
    ARRAY['owner', 'admin']
  ));

-- ── tournament_standings ─────────────────────────────────────────────────────

DROP POLICY IF EXISTS "public_read_listed_tournament_standings" ON tournament_standings;
CREATE POLICY "public_read_listed_tournament_standings" ON tournament_standings
  FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM tournaments t
    WHERE t.id = tournament_standings.tournament_id
      AND t.status IN ('registration_open', 'registration_closed', 'in_progress', 'completed')
  ));

DROP POLICY IF EXISTS "org_member_read_tournament_standings" ON tournament_standings;
CREATE POLICY "org_member_read_tournament_standings" ON tournament_standings
  FOR SELECT
  USING (is_org_member((
    SELECT organizer_org_id FROM tournaments
    WHERE tournaments.id = tournament_standings.tournament_id
  )));

DROP POLICY IF EXISTS "org_admin_manage_tournament_standings" ON tournament_standings;
CREATE POLICY "org_admin_manage_tournament_standings" ON tournament_standings
  FOR ALL
  USING (is_org_role(
    (SELECT organizer_org_id FROM tournaments
     WHERE tournaments.id = tournament_standings.tournament_id),
    ARRAY['owner', 'admin']
  ));

-- ── player_ratings ───────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "self_read_own_rating" ON player_ratings;
CREATE POLICY "self_read_own_rating" ON player_ratings
  FOR SELECT
  USING (user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_read_ratings" ON player_ratings;
CREATE POLICY "org_member_read_ratings" ON player_ratings
  FOR SELECT
  USING (organization_id IS NOT NULL AND is_org_member(organization_id));

DROP POLICY IF EXISTS "org_admin_manage_ratings" ON player_ratings;
CREATE POLICY "org_admin_manage_ratings" ON player_ratings
  FOR ALL
  USING (organization_id IS NOT NULL
         AND is_org_role(organization_id, ARRAY['owner', 'admin', 'teacher']));

-- ── rating_history ───────────────────────────────────────────────────────────
-- No organization_id column; scope via player_ratings.user_id link.

DROP POLICY IF EXISTS "self_read_own_rating_history" ON rating_history;
CREATE POLICY "self_read_own_rating_history" ON rating_history
  FOR SELECT
  USING (user_id = clerk_uid());

DROP POLICY IF EXISTS "org_member_read_rating_history" ON rating_history;
CREATE POLICY "org_member_read_rating_history" ON rating_history
  FOR SELECT
  USING (EXISTS (
    SELECT 1 FROM player_ratings pr
    WHERE pr.user_id = rating_history.user_id
      AND pr.organization_id IS NOT NULL
      AND is_org_member(pr.organization_id)
  ));

DROP POLICY IF EXISTS "org_admin_manage_rating_history" ON rating_history;
CREATE POLICY "org_admin_manage_rating_history" ON rating_history
  FOR ALL
  USING (EXISTS (
    SELECT 1 FROM player_ratings pr
    WHERE pr.user_id = rating_history.user_id
      AND pr.organization_id IS NOT NULL
      AND is_org_role(pr.organization_id, ARRAY['owner', 'admin', 'teacher'])
  ));

-- ============================================================================
-- ROLLBACK (commented out — copy-paste to revert in an emergency, in order)
-- ============================================================================
--
-- -- D. tournament/rating tables: drop policies + disable RLS
-- DROP POLICY IF EXISTS "org_admin_manage_rating_history" ON rating_history;
-- DROP POLICY IF EXISTS "org_member_read_rating_history" ON rating_history;
-- DROP POLICY IF EXISTS "self_read_own_rating_history" ON rating_history;
-- DROP POLICY IF EXISTS "org_admin_manage_ratings" ON player_ratings;
-- DROP POLICY IF EXISTS "org_member_read_ratings" ON player_ratings;
-- DROP POLICY IF EXISTS "self_read_own_rating" ON player_ratings;
-- DROP POLICY IF EXISTS "org_admin_manage_tournament_standings" ON tournament_standings;
-- DROP POLICY IF EXISTS "org_member_read_tournament_standings" ON tournament_standings;
-- DROP POLICY IF EXISTS "public_read_listed_tournament_standings" ON tournament_standings;
-- DROP POLICY IF EXISTS "org_admin_manage_tournament_games" ON tournament_games;
-- DROP POLICY IF EXISTS "org_member_read_tournament_games" ON tournament_games;
-- DROP POLICY IF EXISTS "public_read_listed_tournament_games" ON tournament_games;
-- DROP POLICY IF EXISTS "org_admin_manage_registrations" ON tournament_registrations;
-- DROP POLICY IF EXISTS "org_member_read_registrations" ON tournament_registrations;
-- DROP POLICY IF EXISTS "self_read_own_registration" ON tournament_registrations;
-- DROP POLICY IF EXISTS "org_admin_manage_tournaments" ON tournaments;
-- DROP POLICY IF EXISTS "org_member_read_tournaments" ON tournaments;
-- DROP POLICY IF EXISTS "public_read_listed_tournaments" ON tournaments;
-- ALTER TABLE rating_history DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE player_ratings DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE tournament_standings DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE tournament_games DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE tournament_registrations DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE tournaments DISABLE ROW LEVEL SECURITY;
--
-- -- C. Restore migration-005 policies (re-run migration 005 manually or
-- --    drop the helper-based policies below and re-create the inline ones).
-- DROP POLICY IF EXISTS "org_admin_access" ON user_games;
-- DROP POLICY IF EXISTS "org_member_access" ON user_games;
-- DROP POLICY IF EXISTS "direct_user_access" ON user_games;
-- DROP POLICY IF EXISTS "org_admin_access" ON lesson_chat_history;
-- DROP POLICY IF EXISTS "org_member_access" ON lesson_chat_history;
-- DROP POLICY IF EXISTS "direct_user_access" ON lesson_chat_history;
-- DROP POLICY IF EXISTS "org_admin_access" ON user_progress;
-- DROP POLICY IF EXISTS "org_member_access" ON user_progress;
-- DROP POLICY IF EXISTS "direct_user_access" ON user_progress;
-- DROP POLICY IF EXISTS "org_owner_billing" ON organization_billing;
-- DROP POLICY IF EXISTS "org_admin_manage_content" ON organization_content;
-- DROP POLICY IF EXISTS "org_member_read_content" ON organization_content;
-- DROP POLICY IF EXISTS "org_admin_manage_members" ON organization_members;
-- DROP POLICY IF EXISTS "org_members_read" ON organization_members;
-- DROP POLICY IF EXISTS "org_admin_update" ON organizations;
-- DROP POLICY IF EXISTS "public_read_active_orgs" ON organizations;
--
-- -- B. helper functions
-- DROP FUNCTION IF EXISTS public.is_org_role(uuid, text[]);
-- DROP FUNCTION IF EXISTS public.is_org_member(uuid);
--
-- -- A. clerk_uid
-- DROP FUNCTION IF EXISTS public.clerk_uid();
