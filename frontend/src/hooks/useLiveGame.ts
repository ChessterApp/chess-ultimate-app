'use client';

/**
 * useLiveGame — owns all client state for a challenge-link live game (phase 3).
 *
 * Truth model: Postgres is authoritative. The hook hydrates from
 * `GET /api/games/[gameId]` on mount and again on every Realtime (re)connect,
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
  type MoveEntry,
  type PlayerColor,
  type TerminalInfo,
} from './liveGameState';

/** A move argument accepted by `makeMove` — either raw UCI or squares. */
export type MoveInput =
  | string
  | { from: string; to: string; promotion?: string };

function toUci(move: MoveInput): string {
  if (typeof move === 'string') return move.trim().toLowerCase();
  return `${move.from}${move.to}${move.promotion ?? ''}`.toLowerCase();
}

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
  colorChoice: string;
  initialSec: number | null;
  incrementSec: number | null;
  creatorId: string;
  loading: boolean;
  error: string | null;
  makeMove: (move: MoveInput) => Promise<boolean>;
  join: () => Promise<boolean>;
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

  // Stable token getter for the Supabase client (Clerk's getToken accepts
  // optional options — narrow it to the () => Promise<string|null> shape).
  const tokenFn = useCallback(() => getToken(), [getToken]);

  const safeDispatch = useCallback((action: Parameters<typeof dispatch>[0]) => {
    if (mountedRef.current) dispatch(action);
  }, []);

  /** Re-fetch the authoritative hydration payload and seed the reducer. */
  const hydrate = useCallback(async (): Promise<void> => {
    try {
      const res = await fetch(`/api/games/${gameId}`, { cache: 'no-store' });
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
      setError(null);
    } catch {
      if (mountedRef.current) setError('network_error');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [gameId, safeDispatch]);

  // ── Subscribe: hydrate + private channel + presence + reconnect resync ──────
  useEffect(() => {
    mountedRef.current = true;
    if (!isLoaded || !gameId) return;

    const client = createClerkSupabaseClient(tokenFn);
    clientRef.current = client;

    let channel: RealtimeChannel | null = null;
    let cancelled = false;

    const setup = async () => {
      // Push a fresh Clerk token onto the socket before joining the private
      // channel — the broadcast/presence RLS runs against this token.
      await setRealtimeAuth(client, tokenFn);
      if (cancelled) return;

      channel = client.channel(`game:${gameId}`, {
        config: { private: true, presence: { key: userId ?? 'anon' } },
      });
      channelRef.current = channel;

      const syncPresence = () => {
        if (!channel || !mountedRef.current) return;
        const presence = channel.presenceState();
        const others = Object.keys(presence).filter((k) => k !== userId);
        setOpponentConnected(others.length > 0);
      };

      channel
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
        .on('presence', { event: 'sync' }, syncPresence)
        .on('presence', { event: 'join' }, syncPresence)
        .on('presence', { event: 'leave' }, syncPresence)
        .subscribe(async (subStatus) => {
          if (subStatus === 'SUBSCRIBED') {
            // Reconnect resync: DB is truth, re-hydrate on every (re)connect so
            // a dropped socket / refresh never loses state.
            await hydrate();
            if (!cancelled && channel) {
              await channel.track({ userId: userId ?? 'anon' });
            }
          }
        });
    };

    // Kick an immediate hydration too, so the UI paints from truth even before
    // the socket handshake completes.
    void hydrate();
    void setup();

    return () => {
      cancelled = true;
      if (channel) {
        void client.removeChannel(channel);
      }
      channelRef.current = null;
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

  // ── Actions ────────────────────────────────────────────────────────────────
  const makeMove = useCallback(
    async (move: MoveInput): Promise<boolean> => {
      const uci = toUci(move);
      try {
        const res = await fetch(`/api/games/${gameId}/move`, {
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
      const res = await fetch(`/api/games/${gameId}/join`, { method: 'POST' });
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
    colorChoice: state.colorChoice,
    initialSec: state.initialSec,
    incrementSec: state.incrementSec,
    creatorId: state.creatorId,
    loading,
    error,
    makeMove,
    join,
    refetch: hydrate,
  };
}
