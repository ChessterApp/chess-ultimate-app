'use client';

/**
 * useLiveGame — owns all client state for a challenge-link live game (phase 3).
 *
 * Truth model: Postgres is authoritative. The hook hydrates from
 * `GET /api/live-games/[gameId]` on mount and again on every Realtime (re)connect,
 * then applies `game.start` / `game.move` / `game.end` broadcasts on top via the
 * pure `liveGameReducer`. A dropped socket or page refresh therefore never loses
 * state — the reconnect re-hydration re-establishes truth (the classic
 * Supabase-realtime-game bug this guards against).
 *
 * The private channel `game:{id}` carries the broadcasts + presence; the Clerk
 * JWT is pushed onto the socket via `setRealtimeAuth` before subscribing so the
 * `realtime.messages` RLS accepts us.
 */

import {
  useReducer,
  useEffect,
  useRef,
  useCallback,
  useState,
  useMemo,
} from 'react';
import { useAuth } from '@clerk/nextjs';
import type { RealtimeChannel, SupabaseClient } from '@supabase/supabase-js';
import { createClerkSupabaseClient, setRealtimeAuth } from '@/lib/supabase';
import type {
  GameStatus,
  Turn,
  Clocks,
  HydrationPayload,
  GameStartPayload,
  GameMovePayload,
  GameEndPayload,
  GameDrawOfferPayload,
} from '@/lib/live-game/types';
import {
  liveGameReducer,
  emptyLiveGameState,
  deriveTurn,
  deriveMyColor,
  deriveOrientation,
  deriveIsMyTurn,
  deriveIsCreator,
  deriveClocks,
  deriveTerminal,
  deriveDrawOffer,
  deriveAutoFlag,
  type MoveEntry,
  type PlayerColor,
  type TerminalInfo,
  type DrawOfferInfo,
} from './liveGameState';

/** A move argument accepted by `makeMove` — either raw UCI or squares. */
export type MoveInput =
  | string
  | { from: string; to: string; promotion?: string };

function toUci(move: MoveInput): string {
  if (typeof move === 'string') return move.trim().toLowerCase();
  return `${move.from}${move.to}${move.promotion ?? ''}`.toLowerCase();
}

/** How long an opponent may be absent from presence before we show the banner. */
const PRESENCE_GRACE_MS = 7000;
/** Realtime auth-token refresh cadence — well under Clerk's ~60s token TTL. */
const TOKEN_REFRESH_MS = 30000;
/** Backoff bounds for resubscribing after a channel error. */
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
/** Active-game safety-net re-hydration cadence (dead socket → frozen board). */
const ACTIVE_POLL_MS = 5000;

export interface UseLiveGame {
  status: GameStatus;
  fen: string;
  ply: number;
  turn: Turn;
  orientation: PlayerColor;
  myColor: PlayerColor | null;
  isMyTurn: boolean;
  isCreator: boolean;
  clocks: Clocks;
  moves: MoveEntry[];
  opponentConnected: boolean;
  terminal: TerminalInfo;
  drawOffer: DrawOfferInfo;
  /** True while active with <2 plies played — an abort is legal. */
  canAbort: boolean;
  colorChoice: string;
  initialSec: number | null;
  incrementSec: number | null;
  creatorId: string;
  loading: boolean;
  error: string | null;
  makeMove: (move: MoveInput) => Promise<boolean>;
  join: () => Promise<boolean>;
  resign: () => Promise<boolean>;
  offerDraw: () => Promise<boolean>;
  acceptDraw: () => Promise<boolean>;
  declineDraw: () => Promise<boolean>;
  claimFlag: () => Promise<boolean>;
  abort: () => Promise<boolean>;
  refetch: () => Promise<void>;
}

export function useLiveGame(gameId: string): UseLiveGame {
  const { userId, getToken, isLoaded } = useAuth();
  const [state, dispatch] = useReducer(liveGameReducer, undefined, () =>
    emptyLiveGameState(),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [opponentConnected, setOpponentConnected] = useState(false);
  // Cosmetic clock tick — re-render cadence for the non-authoritative countdown.
  const [now, setNow] = useState<number>(() => Date.now());

  const mountedRef = useRef(true);
  const clientRef = useRef<SupabaseClient | null>(null);
  const channelRef = useRef<RealtimeChannel | null>(null);
  // Disconnect grace timer + whether the opponent has ever been present, so the
  // pre-join waiting state never surfaces a "disconnected" banner.
  const presenceGraceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const opponentEverConnectedRef = useRef(false);
  // Telemetry de-dupe: `action(+detail)` → last-sent epoch ms.
  const telemetryRef = useRef<Record<string, number>>({});

  // Stable token getter for the Supabase client (Clerk's getToken accepts
  // optional options — narrow it to the () => Promise<string|null> shape).
  // The `supabase` JWT template adds the `role: authenticated` claim that
  // Supabase third-party auth requires; the default session token lacks it.
  const tokenFn = useCallback(() => getToken({ template: 'supabase' }), [getToken]);

  const safeDispatch = useCallback((action: Parameters<typeof dispatch>[0]) => {
    if (mountedRef.current) dispatch(action);
  }, []);

  /**
   * Fire-and-forget client telemetry → `POST /telemetry`. Never awaited, never
   * throws into a render/effect path, and de-duped per `action(+detail)` within
   * `minIntervalMs` so realtime churn can't spam the log.
   */
  const sendTelemetry = useCallback(
    (
      action: string,
      detail?: Record<string, unknown>,
      minIntervalMs = 2000,
    ): void => {
      const key = detail ? `${action}:${JSON.stringify(detail)}` : action;
      const at = Date.now();
      if (at - (telemetryRef.current[key] ?? 0) < minIntervalMs) return;
      telemetryRef.current[key] = at;
      try {
        void fetch(`/api/live-games/${gameId}/telemetry`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(detail ? { action, detail } : { action }),
          keepalive: true,
        }).catch(() => {});
      } catch {
        /* telemetry must never surface an error */
      }
    },
    [gameId],
  );

  /** Re-fetch the authoritative hydration payload and seed the reducer. */
  const hydrate = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`/api/live-games/${gameId}`, { cache: 'no-store' });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        if (mountedRef.current) {
          setError(body.error || (res.status === 404 ? 'not_found' : 'load_failed'));
        }
        return;
      }
      const payload = (await res.json()) as HydrationPayload;
      if (!mountedRef.current) return;
      safeDispatch({ type: 'hydrate', payload, at: Date.now() });
      // A successful hydrate clears load/network errors, but must NOT clear a
      // standing 'realtime_error' — the socket is still down even though the DB
      // is reachable; only a fresh SUBSCRIBED clears that banner.
      setError((prev) => (prev === 'realtime_error' ? prev : null));
    } catch {
      if (mountedRef.current) setError('network_error');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [gameId, safeDispatch]);

  // ── Subscribe: hydrate + private channel + presence + reconnect resync ──────
  // Owns the whole realtime lifecycle: initial hydrate, private-channel
  // subscribe, presence (with a disconnect grace period), a 30s token refresh so
  // the short-lived Clerk JWT never lets the socket die mid-game, and an
  // exponential-backoff resubscribe (with re-hydration) on channel errors.
  useEffect(() => {
    mountedRef.current = true;
    if (!isLoaded || !gameId) return;

    const client = createClerkSupabaseClient(tokenFn);
    clientRef.current = client;

    let cancelled = false;
    let channel: RealtimeChannel | null = null;
    let backoffMs = RECONNECT_BASE_MS;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const teardownChannel = () => {
      const c = channel;
      channel = null;
      channelRef.current = null;
      if (c) void client.removeChannel(c);
    };

    const scheduleReconnect = (reason: string) => {
      if (cancelled || reconnectTimer) return;
      teardownChannel();
      const delay = backoffMs;
      backoffMs = Math.min(backoffMs * 2, RECONNECT_MAX_MS);
      sendTelemetry('resubscribe', { reason, delayMs: delay });
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        void connect();
      }, delay);
    };

    // Presence with a grace window: only flip to "disconnected" after the
    // opponent has been continuously absent for PRESENCE_GRACE_MS. A rejoin
    // clears the timer (and the banner) immediately; the pre-join waiting state
    // (opponent never present) shows no banner at all.
    const syncPresence = (thisChannel: RealtimeChannel) => {
      if (cancelled || thisChannel !== channel || !mountedRef.current) return;
      const presence = thisChannel.presenceState();
      const others = Object.keys(presence).filter((k) => k !== userId);
      if (others.length > 0) {
        opponentEverConnectedRef.current = true;
        if (presenceGraceRef.current) {
          clearTimeout(presenceGraceRef.current);
          presenceGraceRef.current = null;
        }
        setOpponentConnected(true);
        sendTelemetry('presence_join');
        return;
      }
      if (!opponentEverConnectedRef.current) {
        setOpponentConnected(false);
        return;
      }
      sendTelemetry('presence_leave');
      if (!presenceGraceRef.current) {
        presenceGraceRef.current = setTimeout(() => {
          presenceGraceRef.current = null;
          if (mountedRef.current) {
            setOpponentConnected(false);
            sendTelemetry('disconnect_shown');
          }
        }, PRESENCE_GRACE_MS);
      }
    };

    const connect = async () => {
      if (cancelled) return;
      // Push a fresh Clerk token onto the socket before joining the private
      // channel — the broadcast/presence RLS runs against this token.
      await setRealtimeAuth(client, tokenFn);
      if (cancelled) return;

      const thisChannel = client.channel(`game:${gameId}`, {
        config: { private: true, presence: { key: userId ?? 'anon' } },
      });
      channel = thisChannel;
      channelRef.current = thisChannel;

      const onPresence = () => syncPresence(thisChannel);

      thisChannel
        .on('broadcast', { event: 'game.start' }, ({ payload }) => {
          safeDispatch({
            type: 'start',
            payload: payload as GameStartPayload,
            at: Date.now(),
          });
        })
        .on('broadcast', { event: 'game.move' }, ({ payload }) => {
          safeDispatch({
            type: 'move',
            payload: payload as GameMovePayload,
            at: Date.now(),
          });
        })
        .on('broadcast', { event: 'game.end' }, ({ payload }) => {
          safeDispatch({
            type: 'end',
            payload: payload as GameEndPayload,
            at: Date.now(),
          });
        })
        .on('broadcast', { event: 'game.draw_offer' }, ({ payload }) => {
          safeDispatch({
            type: 'draw_offer',
            payload: payload as GameDrawOfferPayload,
            at: Date.now(),
          });
        })
        .on('broadcast', { event: 'game.draw_decline' }, ({ payload }) => {
          safeDispatch({
            type: 'draw_decline',
            payload: payload as { gameId: string },
            at: Date.now(),
          });
        })
        .on('presence', { event: 'sync' }, onPresence)
        .on('presence', { event: 'join' }, onPresence)
        .on('presence', { event: 'leave' }, onPresence)
        .subscribe(async (subStatus) => {
          if (cancelled || thisChannel !== channel) return;
          sendTelemetry('channel_status', { status: subStatus });
          if (subStatus === 'SUBSCRIBED') {
            // Recovered — reset backoff, clear any error, and re-hydrate (DB is
            // truth) so a dropped socket / refresh never loses state.
            backoffMs = RECONNECT_BASE_MS;
            if (mountedRef.current) setError(null);
            await hydrate();
            if (!cancelled && thisChannel === channel) {
              await thisChannel.track({ userId: userId ?? 'anon' });
            }
          } else if (
            subStatus === 'CHANNEL_ERROR' ||
            subStatus === 'TIMED_OUT' ||
            subStatus === 'CLOSED'
          ) {
            // Socket dropped (token death, blip, server close). Surface it,
            // re-hydrate from the authoritative DB to catch anything missed,
            // then resubscribe with backoff. Not fatal — the poll below and the
            // reconnect both advance state from truth.
            if (mountedRef.current) setError('realtime_error');
            void hydrate();
            scheduleReconnect(subStatus);
          }
        });
    };

    // Kick an immediate hydration too, so the UI paints from truth even before
    // the socket handshake completes.
    void hydrate();
    void connect();

    // Refresh the Realtime auth token on an interval. Clerk template tokens
    // expire in ~60s; without this the socket silently dies mid-game and the
    // peer sees a presence 'leave' / frozen board.
    const refreshTimer = setInterval(() => {
      if (cancelled) return;
      void (async () => {
        const token = await tokenFn();
        if (cancelled) return;
        client.realtime.setAuth(token ?? undefined);
        sendTelemetry('token_refresh');
      })();
    }, TOKEN_REFRESH_MS);

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(refreshTimer);
      if (presenceGraceRef.current) {
        clearTimeout(presenceGraceRef.current);
        presenceGraceRef.current = null;
      }
      teardownChannel();
      clientRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, userId, isLoaded]);

  // Track mount lifetime independently of the subscribe effect's deps.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Cosmetic countdown: tick only while the game is active.
  useEffect(() => {
    if (state.status !== 'active') return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [state.status]);

  // Waiting-screen safety net: while the creator sits on 'challenge', re-hydrate
  // from the authoritative DB on an interval so the board still appears even if
  // the `game.start` broadcast never arrives (silent realtime failure). Stops as
  // soon as status leaves 'challenge' (active/finished/aborted/expired).
  useEffect(() => {
    if (state.status !== 'challenge') return;
    const id = setInterval(() => {
      void hydrate();
    }, 5000);
    return () => clearInterval(id);
  }, [state.status, hydrate]);

  // Active-game safety net: while the game is live, re-hydrate from the
  // authoritative DB every 5s so a silently-dead socket can't leave the board
  // frozen mid-game. The reducer's ply guard dedupes this against broadcasts, so
  // it's idempotent. Telemetry is throttled hard (30s) to stay out of the way.
  useEffect(() => {
    if (state.status !== 'active') return;
    const id = setInterval(() => {
      void hydrate();
      sendTelemetry('poll_fallback_hydrate', undefined, 30000);
    }, ACTIVE_POLL_MS);
    return () => clearInterval(id);
  }, [state.status, hydrate, sendTelemetry]);

  // ── Actions ────────────────────────────────────────────────────────────────
  const makeMove = useCallback(
    async (move: MoveInput): Promise<boolean> => {
      const uci = toUci(move);
      try {
        const res = await fetch(`/api/live-games/${gameId}/move`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uci }),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as {
            error?: string;
          };
          if (mountedRef.current) setError(body.error || 'move_failed');
          return false;
        }
        // Reconcile immediately from the server's response (the matching
        // broadcast is then a no-op via the reducer's ply guard).
        const payload = (await res.json()) as GameMovePayload;
        safeDispatch({ type: 'move', payload, at: Date.now() });
        if (mountedRef.current) setError(null);
        return true;
      } catch {
        if (mountedRef.current) setError('network_error');
        return false;
      }
    },
    [gameId, safeDispatch],
  );

  const join = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`/api/live-games/${gameId}/join`, { method: 'POST' });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { error?: string };
        if (mountedRef.current) setError(body.error || 'join_failed');
        return false;
      }
      // The join response resolves colours/clocks; re-hydrate for the full
      // authoritative view (the creator flips via the game.start broadcast).
      await hydrate();
      return true;
    } catch {
      if (mountedRef.current) setError('network_error');
      return false;
    }
  }, [gameId, hydrate]);

  // Lifecycle actions that end the game (resign / claim-flag / accept-draw /
  // abort) all return a game.end payload — POST, then reconcile via the reducer
  // (the matching broadcast is then an idempotent no-op).
  const endAction = useCallback(
    async (path: string, body?: unknown, quiet = false): Promise<boolean> => {
      try {
        const res = await fetch(`/api/live-games/${gameId}/${path}`, {
          method: 'POST',
          ...(body !== undefined
            ? {
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
              }
            : {}),
        });
        if (!res.ok) {
          const b = (await res.json().catch(() => ({}))) as { error?: string };
          if (mountedRef.current && !quiet) setError(b.error || `${path}_failed`);
          return false;
        }
        const payload = (await res.json()) as GameEndPayload;
        safeDispatch({ type: 'end', payload, at: Date.now() });
        if (mountedRef.current && !quiet) setError(null);
        return true;
      } catch {
        if (mountedRef.current && !quiet) setError('network_error');
        return false;
      }
    },
    [gameId, safeDispatch],
  );

  const resign = useCallback(() => endAction('resign'), [endAction]);
  const acceptDraw = useCallback(
    () => endAction('draw', { action: 'accept' }),
    [endAction],
  );
  const abort = useCallback(() => endAction('abort'), [endAction]);

  // Auto-flag: fired by the countdown effect below, so it must stay quiet — a
  // benign 'not_flagged' race (clock drift) should never surface an error.
  const claimFlag = useCallback(
    () => endAction('claim-flag', undefined, true),
    [endAction],
  );

  const offerDraw = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`/api/live-games/${gameId}/draw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'offer' }),
      });
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as { error?: string };
        if (mountedRef.current) setError(b.error || 'draw_failed');
        return false;
      }
      safeDispatch({
        type: 'draw_offer',
        payload: { gameId, by: userId ?? '' },
        at: Date.now(),
      });
      if (mountedRef.current) setError(null);
      return true;
    } catch {
      if (mountedRef.current) setError('network_error');
      return false;
    }
  }, [gameId, userId, safeDispatch]);

  const declineDraw = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch(`/api/live-games/${gameId}/draw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'decline' }),
      });
      if (!res.ok) {
        const b = (await res.json().catch(() => ({}))) as { error?: string };
        if (mountedRef.current) setError(b.error || 'draw_failed');
        return false;
      }
      safeDispatch({ type: 'draw_decline', payload: { gameId }, at: Date.now() });
      if (mountedRef.current) setError(null);
      return true;
    } catch {
      if (mountedRef.current) setError('network_error');
      return false;
    }
  }, [gameId, safeDispatch]);

  // Auto-flag detection: when the player-to-move's cosmetic clock hits 0, fire a
  // single guarded claimFlag(). The ref resets whenever the game leaves 'active'
  // so a later game can flag again; the server re-verifies before ending.
  const flagClaimedRef = useRef(false);
  useEffect(() => {
    if (state.status !== 'active') {
      flagClaimedRef.current = false;
      return;
    }
    if (flagClaimedRef.current) return;
    if (deriveAutoFlag(state, now) !== null) {
      flagClaimedRef.current = true;
      void claimFlag();
    }
  }, [state, now, claimFlag]);

  // ── Derived, view-facing state ──────────────────────────────────────────────
  const clocks = useMemo(() => deriveClocks(state, now), [state, now]);

  return {
    status: state.status,
    fen: state.fen,
    ply: state.ply,
    turn: deriveTurn(state),
    orientation: deriveOrientation(state, userId ?? null),
    myColor: deriveMyColor(state, userId ?? null),
    isMyTurn: deriveIsMyTurn(state, userId ?? null),
    isCreator: deriveIsCreator(state, userId ?? null),
    clocks,
    moves: state.moves,
    opponentConnected,
    terminal: deriveTerminal(state, userId ?? null),
    drawOffer: deriveDrawOffer(state, userId ?? null),
    canAbort: state.status === 'active' && state.ply < 2,
    colorChoice: state.colorChoice,
    initialSec: state.initialSec,
    incrementSec: state.incrementSec,
    creatorId: state.creatorId,
    loading,
    error,
    makeMove,
    join,
    resign,
    offerDraw,
    acceptDraw,
    declineDraw,
    claimFlag,
    abort,
    refetch: hydrate,
  };
}
