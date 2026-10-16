-- Migration 056: per-move voice notes for the Database section.
--
-- A voice note is a short audio clip (<= 2 min, <= 5 MB) attached to ONE move of
-- a saved user game. The PGN stays a plain chess file: notes map to moves by
-- node_path, the move's SAN path from the start position joined by single spaces
-- (e.g. 'e4 e5 Nf3'). SAN paths survive re-parsing and main-line promotion, and a
-- deleted move takes every note at or under its path with it.
--
-- Audio lives in the PRIVATE `move-voice-notes` bucket under
-- `{owner_user_id}/{game_id}/{uuid}.{ext}` and is only ever served through
-- short-lived signed URLs minted by the Flask backend (service role). Like the
-- other user_databases tables, the table is RLS-enabled with no policies, so
-- only the service role can read or write it.
--
-- delete_user_data is re-created from 055 with move_voice_notes added; the
-- user-data manifest test now reads this file.
--
-- Idempotent: safe to re-run.

-- ============================================================================
-- A. Private storage bucket
-- ============================================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('move-voice-notes', 'move-voice-notes', false, 5242880, ARRAY['audio/*'])
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- B. move_voice_notes
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.move_voice_notes (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  game_id uuid NOT NULL REFERENCES public.user_games(id) ON DELETE CASCADE,
  owner_user_id text NOT NULL,
  node_path text NOT NULL,
  storage_path text NOT NULL UNIQUE,
  mime_type text NOT NULL,
  duration_ms integer NOT NULL CHECK (duration_ms > 0 AND duration_ms <= 122000),
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_move_voice_notes_game ON public.move_voice_notes(game_id);
CREATE INDEX IF NOT EXISTS idx_move_voice_notes_owner ON public.move_voice_notes(owner_user_id);

ALTER TABLE public.move_voice_notes ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- C. delete_user_data (re-created from 055 + move_voice_notes)
-- ============================================================================

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

  -- Move voice notes (056) are children of user_games (the FK cascades too).
  -- Their storage objects are removed by the Clerk webhook before this runs.
  delete from public.move_voice_notes where owner_user_id = p_clerk_id;
  GET DIAGNOSTICS n = ROW_COUNT; result := result || jsonb_build_object('move_voice_notes', n);

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
