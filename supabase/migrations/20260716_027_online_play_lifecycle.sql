-- Migration: Online Play (phase 4) — game lifecycle (draw offers).
-- Parent plan:  /root/clawd/plans/chesster-online-play-challenge-link.md
-- Phase 4 spec: /root/clawd/plans/chesster-liveplay-phase4-spec.md
--
-- Adds the ONE column phase 4 needs that the phase-1 schema lacks: a place to
-- record a standing draw offer. resign / flag / abort / expiry all reuse
-- existing columns (status / end_reason / winner_id / result), so no other
-- schema change is required.
--
-- Security model unchanged (see 20260716_026_online_play.sql): all game-state
-- writes are performed by Next.js route handlers with the service-role key
-- (BYPASSRLS). `draw_offer_by` is written only by the /draw route, never by a
-- client, so no new RLS policy is needed — the existing player-only SELECT
-- policy already governs who can read it.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS. Safe to re-run.

ALTER TABLE public.games
  ADD COLUMN IF NOT EXISTS draw_offer_by text;  -- Clerk id of the player with a standing draw offer, or NULL

-- ============================================================================
-- ROLLBACK (commented — copy-paste to revert)
-- ============================================================================
-- ALTER TABLE public.games DROP COLUMN IF EXISTS draw_offer_by;
