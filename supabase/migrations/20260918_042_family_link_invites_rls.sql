-- Security lockdown for family_link_invites (2026-09-18)
--
-- Migration 041 created family_link_invites without RLS, leaving the default
-- anon/authenticated grants in place. The table holds single-use accept tokens
-- and target emails and is SERVER-ONLY: every read/write goes through the
-- service-role client (`supabaseAdmin` in src/lib/family-link-invite.ts), never
-- the browser anon client. Its sibling tables (organization_members,
-- invite_email_failures, pending_registrations) all have RLS enabled; this one
-- slipped through.
--
-- service_role has BYPASSRLS + its own grants, so ENABLE RLS + REVOKE from
-- anon/authenticated does NOT affect the app. Matches the server-only lockdown
-- pattern in 20260721_rls_lockdown_server_only.sql. Idempotent, fully reversible.

BEGIN;

ALTER TABLE public.family_link_invites ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.family_link_invites FROM anon;
REVOKE ALL ON public.family_link_invites FROM authenticated;

COMMIT;

-- Rollback:
-- ALTER TABLE public.family_link_invites DISABLE ROW LEVEL SECURITY;
-- GRANT ALL ON public.family_link_invites TO anon, authenticated;
