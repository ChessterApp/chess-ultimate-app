-- Security fix: Supabase Security Advisor rls_disabled_in_public (2026-07-21)
-- Locks down the 9 flagged public tables that are SERVER-ONLY:
--   * not in the `powersync` logical-replication publication (no client sync)
--   * never queried by the browser anon client (verified across frontend/src)
--   * only accessed by the Flask backend + Next.js server routes via service_role
--
-- service_role has BYPASSRLS and its own grants, so ENABLE RLS + REVOKE from
-- anon/authenticated does NOT affect backend access. Fully reversible.
--
-- DEFERRED (NOT in this migration) — the 8 PowerSync-published tables:
--   analysis_conversations, courses, lesson_puzzles, lessons, opening_nodes,
--   opening_repertoires, subscriptions, user_puzzle_progress.
--   These are synced to clients and some are written back via the anon client
--   (opening_repertoires/opening_nodes/analysis_conversations). Locking them
--   requires configuring Clerk as a Supabase JWT issuer (third-party auth) so
--   anon writes carry a user identity, then adding user-scoped RLS policies.
--   Tracked as a follow-up.

BEGIN;

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'ai_response_cache',
    'analysis_chat_messages',
    'api_usage',
    'modules',
    'opening_arrows',
    'opening_game_links',
    'pending_onboarding',
    'promo_codes',
    'subscription_events'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon;', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM authenticated;', t);
  END LOOP;
END $$;

COMMIT;
