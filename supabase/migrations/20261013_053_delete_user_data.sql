-- ============================================================================
-- 20261013_053_delete_user_data.sql
-- P1 — account deletion removes ALL of a user's data in one transaction.
--
-- public.delete_user_data(p_clerk_id) is called by the Clerk `user.deleted`
-- webhook (service role). It runs inside the caller's single transaction: any
-- error rolls the whole deletion back and is raised, so the webhook returns 500
-- and Svix retries. Idempotent: a replay finds nothing and returns zero counts.
-- Returns jsonb {table | table.column: rows_affected} for logging.
--
-- The decision for every Clerk-id column lives in
-- frontend/src/lib/user-data-manifest.ts; its test keeps this file in sync.
--
--   DELETE   personal rows (children before parents).
--   NULLIFY  shared rows keep existing, the link to the person is set NULL.
--   KEEP     (never touched here):
--     platform_admin_audit_log.admin_clerk_id — append-only, DELETE is blocked
--       by trigger; the audit trail of admin actions must survive.
--     impersonation_sessions.admin_clerk_id / target_clerk_id — admin security
--       audit (who impersonated whom, when).
--     organization_billing.whop_user_id — org-level billing record, not the
--       member's personal data.
--
-- Tables created by supabase/migrations are referenced statically. Tables that
-- are created elsewhere (Flask / Hermes migrations) or are not present in every
-- environment (player_fide_ratings) are guarded with to_regclass.
--
-- Additive + idempotent. NOT applied to prod (separate approval step).
-- ============================================================================

-- NULLIFY targets must accept NULL.
ALTER TABLE public.tournaments ALTER COLUMN created_by DROP NOT NULL;
ALTER TABLE public.tournament_games ALTER COLUMN white_player_id DROP NOT NULL;
ALTER TABLE public.tournament_games ALTER COLUMN black_player_id DROP NOT NULL;
ALTER TABLE public.wheel_presets ALTER COLUMN created_by DROP NOT NULL;
ALTER TABLE public.invite_jwts_consumed ALTER COLUMN clerk_user_id DROP NOT NULL;

CREATE OR REPLACE FUNCTION public.delete_user_data(p_clerk_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result jsonb := '{}'::jsonb;
  n bigint;
  g record;
BEGIN
  IF p_clerk_id IS NULL OR p_clerk_id = '' THEN
    RAISE EXCEPTION 'delete_user_data: p_clerk_id is required';
  END IF;

  -- ---- DELETE: guarded tables (not created by supabase/migrations) --------
  IF to_regclass('public.coach_messages') IS NOT NULL
     AND to_regclass('public.coach_sessions') IS NOT NULL THEN
    EXECUTE 'delete from public.coach_messages where session_id in '
         || '(select id from public.coach_sessions where user_id = $1)'
      USING p_clerk_id;
    GET DIAGNOSTICS n = ROW_COUNT;
    result := result || jsonb_build_object('coach_messages', n);
  END IF;

  -- Order matters: children before parents.
  FOR g IN
    SELECT * FROM (VALUES
      (1, 'coach_sessions', 'user_id'),
      (2, 'analysis_chat_messages', 'user_id'),
      (3, 'analysis_conversations', 'user_id'),
      (4, 'user_games', 'user_id'),
      (5, 'user_game_collection_shares', 'user_id'),
      (6, 'user_shared_databases', 'subscriber_id'),
      (7, 'user_databases', 'user_id'),
      (8, 'api_usage', 'user_id'),
      (9, 'coach_bestofn_audit', 'user_id'),
      (10, 'coach_corrections', 'user_id'),
      (11, 'coach_curriculum', 'user_id'),
      (12, 'coach_curriculum_audit', 'user_id'),
      (13, 'coach_events', 'user_id'),
      (14, 'coach_feedback', 'user_id'),
      (15, 'coach_game_insights', 'user_id'),
      (16, 'coach_memory_audit', 'user_id'),
      (17, 'token_usage', 'user_id'),
      (18, 'voice_usage', 'user_id'),
      (19, 'lesson_chat_history', 'user_id'),
      (20, 'opening_repertoires', 'user_id'),
      (21, 'player_fide_ratings', 'user_id'),
      (22, 'user_progress', 'user_id'),
      (23, 'user_puzzle_progress', 'user_id'),
      (24, 'subscriptions', 'clerk_user_id'),
      (25, 'user_onboarding', 'clerk_user_id'),
      (26, 'user_profiles', 'user_id')
    ) AS t(ord, tbl, col)
    ORDER BY ord
  LOOP
    IF to_regclass('public.' || g.tbl) IS NOT NULL THEN
      EXECUTE format('delete from public.%I where %I = $1', g.tbl, g.col) USING p_clerk_id;
      GET DIAGNOSTICS n = ROW_COUNT;
      result := result || jsonb_build_object(g.tbl, n);
    END IF;
  END LOOP;

  -- ---- DELETE: tables created by supabase/migrations ----------------------
  -- Companion (task_attempt before task_assignment).
  delete from public.task_attempt where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('task_attempt', n);
  delete from public.task_assignment where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('task_assignment', n);
  delete from public.competency_evidence where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('competency_evidence', n);
  delete from public.mastery_state where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('mastery_state', n);
  delete from public.quest_progress where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('quest_progress', n);
  delete from public.companion_weekly_goal where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('companion_weekly_goal', n);
  delete from public.domain_event where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('domain_event', n);
  delete from public.companion where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('companion', n);

  -- Gameplay / learning (puzzle_rush_attempts cascade from puzzle_rush_runs).
  delete from public.live_game_logs where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('live_game_logs', n);
  delete from public.player_ratings where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('player_ratings', n);
  delete from public.rating_history where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('rating_history', n);
  delete from public.puzzle_rush_bests where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('puzzle_rush_bests', n);
  delete from public.puzzle_rush_runs where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('puzzle_rush_runs', n);
  delete from public.puzzle_rush_school_pick where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('puzzle_rush_school_pick', n);
  delete from public.tournament_registrations where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('tournament_registrations', n);
  delete from public.tournament_standings where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('tournament_standings', n);

  -- Identity / membership / linking.
  delete from public.family_link_invites
    where inviter_user_id = p_clerk_id or accepted_by_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('family_link_invites', n);
  delete from public.organization_ownership_transfers
    where current_owner_user_id = p_clerk_id or invitee_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('organization_ownership_transfers', n);
  delete from public.organization_members where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('organization_members', n);
  delete from public.link_attempts where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('link_attempts', n);
  delete from public.pending_onboarding where clerk_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('pending_onboarding', n);
  delete from public.platform_user_cache where clerk_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('platform_user_cache', n);
  delete from public.platform_user_status where clerk_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('platform_user_status', n);

  -- ---- NULLIFY: keep the shared row, drop the link to the person ----------
  update public.tournaments set created_by = null where created_by = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('tournaments.created_by', n);
  update public.tournament_games set white_player_id = null where white_player_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('tournament_games.white_player_id', n);
  update public.tournament_games set black_player_id = null where black_player_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('tournament_games.black_player_id', n);
  update public.branch_invite_tokens set created_by = null where created_by = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('branch_invite_tokens.created_by', n);
  update public.wheel_presets set created_by = null where created_by = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('wheel_presets.created_by', n);
  update public.organization_members set invited_by = null where invited_by = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('organization_members.invited_by', n);
  update public.pending_registrations set claimed_by_clerk_user_id = null where claimed_by_clerk_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('pending_registrations.claimed_by_clerk_user_id', n);
  -- Row stays: its jti_hash is the JWT replay guard.
  update public.invite_jwts_consumed set clerk_user_id = null where clerk_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('invite_jwts_consumed.clerk_user_id', n);

  RETURN result;
END;
$$;

REVOKE ALL ON FUNCTION public.delete_user_data(text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.delete_user_data(text) TO service_role;
