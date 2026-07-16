-- Migration: Online Play (phase 1) — games schema, RLS, Realtime authorization.
-- Parent plan:  /root/clawd/plans/chesster-online-play-challenge-link.md
-- Phase 1 spec: /root/clawd/plans/chesster-liveplay-phase1-spec.md
--
-- Introduces the two tables that back "play a friend via challenge link":
--   * games       — one row is BOTH the challenge (status='challenge') and the
--                   live game after accept (status='active'). challenge id == game id.
--   * game_moves  — append-only move log, one row per ply.
--
-- Security model (matches supabase/migrations/20260601_008_rls_hardening.sql):
--   * Reads: authenticated clients read via RLS using clerk_uid().
--   * Writes: performed only by Next.js route handlers with the service-role
--     key (BYPASSRLS) — there is intentionally NO client UPDATE/INSERT policy on
--     game state, so clocks/positions stay server-authoritative. Clients may
--     INSERT a games row (create a challenge) and that is the only client write.
--   * Realtime: RLS on realtime.messages restricts broadcast/presence on topic
--     `game:{id}` to the two players of that game.
--
-- Realtime auth spike result (2026-07-16):
--   The Clerk-authorized supabase client (accessToken: () => getToken()) carries
--   the `role: authenticated` claim, which is what realtime authorization checks.
--   Policies below apply cleanly and the private channel refuses anon connections
--   (anon has no `authenticated` grant path here). Full spike + how-to-run is in
--   docs/online-play-realtime-spike.md and frontend/scripts/realtime-auth-spike.ts.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS, DROP POLICY IF EXISTS, CREATE OR
-- REPLACE FUNCTION. Safe to re-run.

-- ============================================================================
-- A. Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.games (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- challenge id == game id
  creator_id    text NOT NULL,                                -- Clerk id of challenger
  opponent_id   text,                                         -- set on accept
  white_id      text,                                         -- resolved on accept
  black_id      text,                                         -- resolved on accept
  status        text NOT NULL DEFAULT 'challenge'
                  CHECK (status IN ('challenge','active','finished','aborted','expired')),
  color_choice  text NOT NULL DEFAULT 'random'
                  CHECK (color_choice IN ('white','black','random')),
  initial_sec   int,                                          -- null = untimed
  increment_sec int,                                          -- null = untimed
  fen           text NOT NULL DEFAULT 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  ply           int  NOT NULL DEFAULT 0,
  white_ms      bigint,                                       -- clock bank, ms
  black_ms      bigint,
  last_move_at  timestamptz,
  result        text,                                         -- '1-0' / '0-1' / '1/2-1/2'
  winner_id     text,
  end_reason    text,                                         -- mate/resign/flag/draw/abort
  expires_at    timestamptz DEFAULT (now() + interval '24 hours'),  -- challenge TTL
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.game_moves (
  game_id      uuid NOT NULL REFERENCES public.games(id) ON DELETE CASCADE,
  ply          int  NOT NULL,
  uci          text NOT NULL,
  san          text,
  fen_after    text,
  move_time_ms bigint,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (game_id, ply)
);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_games_creator_id  ON public.games(creator_id);
CREATE INDEX IF NOT EXISTS idx_games_opponent_id ON public.games(opponent_id);
CREATE INDEX IF NOT EXISTS idx_games_status      ON public.games(status);

-- ── updated_at trigger (per-table function convention, see migration 001) ─────
CREATE OR REPLACE FUNCTION public.update_games_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_games_updated_at ON public.games;
CREATE TRIGGER trigger_games_updated_at
  BEFORE UPDATE ON public.games
  FOR EACH ROW
  EXECUTE FUNCTION public.update_games_updated_at();

-- ============================================================================
-- B. is_game_player(game) — SECURITY DEFINER helper (mirrors is_org_member).
--    True when the current Clerk user is one of the game's players. Bypasses
--    RLS on games so it can be reused inside realtime.messages policies without
--    recursion.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.is_game_player(game uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.games g
    WHERE g.id = game
      AND public.clerk_uid() IN (g.creator_id, g.opponent_id, g.white_id, g.black_id)
  );
$$;

REVOKE ALL ON FUNCTION public.is_game_player(uuid) FROM public;
GRANT EXECUTE ON FUNCTION public.is_game_player(uuid) TO anon, authenticated, service_role;

-- ============================================================================
-- C. RLS on public.games
-- ============================================================================

ALTER TABLE public.games ENABLE ROW LEVEL SECURITY;

-- Open challenges are readable by any authenticated user (lobby view before
-- accept); players read their own games in any status.
DROP POLICY IF EXISTS "games_select_challenge_or_player" ON public.games;
CREATE POLICY "games_select_challenge_or_player" ON public.games
  FOR SELECT
  USING (
    status = 'challenge'
    OR clerk_uid() IN (creator_id, opponent_id, white_id, black_id)
  );

-- A client may create a challenge only as itself. Everything else (accept,
-- moves, clocks, end state) is a service-role UPDATE — no client UPDATE policy.
DROP POLICY IF EXISTS "games_insert_self_creator" ON public.games;
CREATE POLICY "games_insert_self_creator" ON public.games
  FOR INSERT
  WITH CHECK (creator_id = clerk_uid());

-- ============================================================================
-- D. RLS on public.game_moves — players read their own game's moves; all
--    writes are service-role only.
-- ============================================================================

ALTER TABLE public.game_moves ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "game_moves_select_player" ON public.game_moves;
CREATE POLICY "game_moves_select_player" ON public.game_moves
  FOR SELECT
  USING (public.is_game_player(game_id));

-- ============================================================================
-- E. Realtime authorization on topic `game:{id}`.
--    Only the two players may receive (SELECT) and send (INSERT) broadcast /
--    presence messages. The game uuid is parsed out of the topic string and
--    checked against games via is_game_player(). A non-matching topic yields
--    NULL → is_game_player(NULL) is false, so the channel refuses.
-- ============================================================================

DROP POLICY IF EXISTS "games_realtime_players_receive" ON realtime.messages;
CREATE POLICY "games_realtime_players_receive" ON realtime.messages
  FOR SELECT
  TO authenticated
  USING (
    realtime.messages.extension IN ('broadcast', 'presence')
    AND public.is_game_player(
      (regexp_match(realtime.topic(), '^game:([0-9a-fA-F-]{36})$'))[1]::uuid
    )
  );

DROP POLICY IF EXISTS "games_realtime_players_send" ON realtime.messages;
CREATE POLICY "games_realtime_players_send" ON realtime.messages
  FOR INSERT
  TO authenticated
  WITH CHECK (
    realtime.messages.extension IN ('broadcast', 'presence')
    AND public.is_game_player(
      (regexp_match(realtime.topic(), '^game:([0-9a-fA-F-]{36})$'))[1]::uuid
    )
  );

-- ============================================================================
-- ROLLBACK (commented — copy-paste to revert, in order)
-- ============================================================================
-- DROP POLICY IF EXISTS "games_realtime_players_send" ON realtime.messages;
-- DROP POLICY IF EXISTS "games_realtime_players_receive" ON realtime.messages;
-- DROP POLICY IF EXISTS "game_moves_select_player" ON public.game_moves;
-- DROP POLICY IF EXISTS "games_insert_self_creator" ON public.games;
-- DROP POLICY IF EXISTS "games_select_challenge_or_player" ON public.games;
-- DROP FUNCTION IF EXISTS public.is_game_player(uuid);
-- DROP TRIGGER IF EXISTS trigger_games_updated_at ON public.games;
-- DROP FUNCTION IF EXISTS public.update_games_updated_at();
-- DROP TABLE IF EXISTS public.game_moves;
-- DROP TABLE IF EXISTS public.games;
