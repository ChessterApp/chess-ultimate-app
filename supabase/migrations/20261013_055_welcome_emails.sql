-- ============================================================================
-- 20261013_055_welcome_emails.sql
-- P4 — welcome drip via Resend (Listmonk dropped).
--
-- welcome_emails: one row per (user, step) of the 5-email welcome sequence,
--   scheduled by the Clerk `user.created` webhook (frontend/src/lib/welcome-drip.ts)
--   and sent by `flask welcome-emails send-due` (backend/services/welcome_drip.py).
-- email_opt_outs: lower-cased addresses that clicked unsubscribe.
--
-- Both are service-role only (RLS on, no anon/authenticated policies).
-- delete_user_data is re-created from 053 with both tables added; the user-data
-- manifest test reads this file as the current definition.
--
-- Additive + idempotent. NOT applied to prod (separate approval step).
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.welcome_emails (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL,
  email text NOT NULL,
  first_name text,
  locale text NOT NULL DEFAULT 'en' CHECK (locale = ANY (ARRAY['en', 'ru', 'kk'])),
  step smallint NOT NULL CHECK (step BETWEEN 1 AND 5),
  scheduled_for timestamptz NOT NULL,
  sent_at timestamptz,
  skipped_reason text,
  error text,
  attempts int NOT NULL DEFAULT 0,
  resend_id text,
  created_at timestamptz DEFAULT now(),
  UNIQUE (user_id, step)
);

CREATE INDEX IF NOT EXISTS welcome_emails_due_idx
  ON public.welcome_emails (scheduled_for)
  WHERE sent_at IS NULL AND skipped_reason IS NULL;

CREATE INDEX IF NOT EXISTS welcome_emails_email_idx
  ON public.welcome_emails (email);

CREATE TABLE IF NOT EXISTS public.email_opt_outs (
  email text PRIMARY KEY CHECK (email = lower(email)),
  user_id text,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE public.welcome_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_opt_outs ENABLE ROW LEVEL SECURITY;

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

  -- Welcome drip (055).
  delete from public.welcome_emails where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('welcome_emails', n);
  delete from public.email_opt_outs where user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('email_opt_outs', n);

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
