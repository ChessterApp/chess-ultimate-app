-- Security fix: Supabase Security Advisor rls_disabled_in_public — Phase 2b (2026-07-22)
-- Follow-up to:
--   * 20260721_rls_lockdown_server_only.sql   (Phase 1, 9 server-only tables)
--   * 20260721_rls_lockdown_synced_readonly.sql (Phase 2a, 5 synced read-only tables)
--
-- Locks down the final 3 PowerSync-published tables that are WRITTEN BACK from the
-- browser via the PowerSync uploadData connector:
--   analysis_conversations, opening_repertoires, opening_nodes.
--
-- REQUIRES the connector Clerk-auth change (Phase 2b, Task 1) to be deployed FIRST:
--   frontend/src/lib/powersync/connector.ts now writes via createClerkSupabaseClient(getToken)
--   so client write-backs carry the Clerk JWT (role: authenticated, sub = user id).
--   If this migration lands before that connector change ships, every client sync
--   write will 401 (writes arrive as `anon`, which this migration REVOKEs).
--
-- Why this is safe for READS: PowerSync replicates from Postgres via its own
-- privileged publication role — client reads never go through the anon PostgREST
-- client, so ENABLE RLS does not break sync reads. Writes now go through the
-- `authenticated` role and are scoped per-user by clerk_uid() (= request.jwt.claims
-- ->> 'sub', see migration 008). service_role has BYPASSRLS + its own grants, so
-- backend access is unaffected — no policy and no REVOKE for service_role. Reversible.

BEGIN;

-- opening_repertoires: owned directly via user_id (text = clerk sub).
ALTER TABLE public.opening_repertoires ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.opening_repertoires FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.opening_repertoires TO authenticated;

CREATE POLICY opening_repertoires_owner ON public.opening_repertoires
  FOR ALL
  TO authenticated
  USING (user_id = public.clerk_uid())
  WITH CHECK (user_id = public.clerk_uid());

-- analysis_conversations: owned directly via user_id (text = clerk sub).
ALTER TABLE public.analysis_conversations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.analysis_conversations FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.analysis_conversations TO authenticated;

CREATE POLICY analysis_conversations_owner ON public.analysis_conversations
  FOR ALL
  TO authenticated
  USING (user_id = public.clerk_uid())
  WITH CHECK (user_id = public.clerk_uid());

-- opening_nodes: no user_id — scoped via parent repertoire ownership.
ALTER TABLE public.opening_nodes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.opening_nodes FROM anon;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.opening_nodes TO authenticated;

CREATE POLICY opening_nodes_via_repertoire ON public.opening_nodes
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.opening_repertoires r
      WHERE r.id = opening_nodes.repertoire_id
        AND r.user_id = public.clerk_uid()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.opening_repertoires r
      WHERE r.id = opening_nodes.repertoire_id
        AND r.user_id = public.clerk_uid()
    )
  );

COMMIT;
