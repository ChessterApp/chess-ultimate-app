-- Migration: Live Play — server/client telemetry log (Stage A).
--
-- Backs diagnosability for online play. One append-only row per live-game
-- request (server) or client-side realtime event (client). There were NO logs
-- for live play, which made the "opponent disconnected / frozen board" class of
-- bugs undiagnosable — this table is written first so the rest is observable.
--
-- Security model (matches supabase/migrations/20260716_026_online_play.sql):
--   * Writes are service-role ONLY (Next.js route handlers). There is
--     intentionally NO client INSERT/SELECT policy — clients never read or write
--     this table directly; the client telemetry endpoint proxies through the
--     service role. RLS is enabled with no policies → all anon/authenticated
--     access is denied by default.
--   * The server logger degrades gracefully if this table is absent (it catches
--     every error and never blocks the response), so applying this migration is
--     not a hard dependency for live play to function.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS, CREATE INDEX IF NOT EXISTS. Safe to
-- re-run.

CREATE TABLE IF NOT EXISTS public.live_game_logs (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at  timestamptz NOT NULL DEFAULT now(),
  game_id     uuid,
  user_id     text,
  source      text NOT NULL CHECK (source IN ('server','client')),
  action      text NOT NULL,
  ply         int,
  outcome     text,
  duration_ms int,
  stages      jsonb,
  detail      jsonb
);

CREATE INDEX IF NOT EXISTS idx_live_game_logs_game_created
  ON public.live_game_logs (game_id, created_at);

-- RLS on, no policies → service-role (BYPASSRLS) writes only; everyone else
-- denied. Clients reach this table exclusively via the telemetry route handler.
ALTER TABLE public.live_game_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- ROLLBACK (commented — copy-paste to revert)
-- ============================================================================
-- DROP INDEX IF EXISTS public.idx_live_game_logs_game_created;
-- DROP TABLE IF EXISTS public.live_game_logs;
