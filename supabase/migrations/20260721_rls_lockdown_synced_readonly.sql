-- Security fix: Supabase Security Advisor rls_disabled_in_public — Phase 2a (2026-07-21)
-- Follow-up to 20260721_rls_lockdown_server_only.sql (Phase 1, 9 server-only tables).
--
-- Locks down 5 of the 8 previously-deferred PowerSync-published tables that are
-- READ-ONLY on the client / written only by the server:
--   * courses, lessons, lesson_puzzles  — reference content, no client writes.
--   * subscriptions                       — written only by the Whop webhook (service_role).
--   * user_puzzle_progress                — written only by the Flask backend (service_role);
--                                           not in the PowerSync local schema, no browser anon access.
--
-- Why this is safe despite these being synced to clients:
--   PowerSync replicates from Postgres via its own privileged publication role — client
--   READS never go through the anon PostgREST client, so ENABLE RLS + REVOKE anon/authenticated
--   does NOT break sync reads. Verified across frontend/src: no browser anon SELECT/INSERT/
--   UPDATE/DELETE on any of these 5 tables (only server routes via service_role touch them).
--   service_role has BYPASSRLS + its own grants, so backend access is unaffected. Reversible.
--
-- STILL DEFERRED (Phase 2b) — the 3 tables written back from the browser via the
-- PowerSync uploadData connector using the bare anon key:
--   analysis_conversations, opening_repertoires, opening_nodes.
--   Locking these first requires switching frontend/src/lib/powersync/connector.ts from the
--   bare anon supabase client to createClerkSupabaseClient(getToken({template:'supabase'}))
--   so write-backs carry the Clerk JWT (role: authenticated, sub = user id); THEN adding
--   user-scoped policies (sub = user_id; opening_nodes joins via repertoire_id -> parent).
--   Doing it as a pure migration now would reject every client UPDATE/DELETE and break the app.
--
-- NOTE: user_progress is intentionally NOT touched here — it already has RLS enabled.

BEGIN;

DO $$
DECLARE
  t text;
  tables text[] := ARRAY[
    'courses',
    'lessons',
    'lesson_puzzles',
    'subscriptions',
    'user_puzzle_progress'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM anon;', t);
    EXECUTE format('REVOKE ALL ON public.%I FROM authenticated;', t);
  END LOOP;
END $$;

COMMIT;
