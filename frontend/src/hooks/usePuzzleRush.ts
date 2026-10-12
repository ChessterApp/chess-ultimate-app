'use client';

/**
 * usePuzzleRush — drives one Puzzle Rush run: countdown, server-validated
 * moves, the §3 feedback/transition timings, server-owned timeout, quit, and
 * on-device guest bests. All board state lives in `runReducer`.
 */

import { useCallback, useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import type { Key } from 'chessground/types';
import { rushApi, RushApiError, type RushAuth } from '@/lib/puzzle-rush/api';
import { initialRunState, runReducer } from '@/lib/puzzle-rush/runReducer';
import { loadGuestToken, recordGuestScore, saveGuestToken, saveLastMode } from '@/lib/puzzle-rush/storage';
import type { RunState, RushMode, RushResults } from '@/lib/puzzle-rush/types';
import { useSoundEffects } from '@/hooks/useSoundEffects';

// §3 implementation targets.
export const TIMINGS = {
  COUNTDOWN_STEP: 750,
  GO_VISIBLE: 1100,
  BADGE_HOLD_OK: 160,
  BADGE_HOLD_FAIL: 240,
  BOARD_CLEAR: 150,
  FADE_IN: 170,
  REVEAL_IN_THREE: 200,
  RESULTS_DELAY: 700,
  COACH_VISIBLE: 2600,
  TIMEOUT_POLL: 500,
  TIMEOUT_POLL_TRIES: 12,
} as const;

export type CountdownStep = 3 | 2 | 1 | 'go' | null;

export function usePuzzleRush(initialMode: RushMode) {
  const { getToken, isSignedIn } = useAuth();
  const { play } = useSoundEffects();
  const [state, dispatch] = useReducer(runReducer, initialMode, initialRunState);
  const [countdown, setCountdown] = useState<CountdownStep>(null);
  const [showResults, setShowResults] = useState(false);
  const [guestPb, setGuestPb] = useState(false);

  // Latest state for async handlers (synced after each commit).
  const stateRef = useRef(state);
  useLayoutEffect(() => {
    stateRef.current = state;
  });
  const guestTokenRef = useRef<string | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  // Bumped per run so late timers / responses from an old run are ignored.
  const genRef = useRef(0);
  const finishedRef = useRef<string | null>(null);

  // Stable identity: Clerk's getToken may change per render, and the deadline
  // effect must not re-arm (and re-poll) because of it.
  const clerkRef = useRef({ getToken, isSignedIn });
  useLayoutEffect(() => {
    clerkRef.current = { getToken, isSignedIn };
  });
  const auth = useCallback((): RushAuth => ({
    getToken: async () => (clerkRef.current.isSignedIn ? clerkRef.current.getToken() : null),
    guestToken: guestTokenRef.current,
  }), []);

  const later = useCallback((ms: number, fn: () => void) => {
    const gen = genRef.current;
    timersRef.current.push(setTimeout(() => {
      if (gen === genRef.current) fn();
    }, ms));
  }, []);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
  }, []);

  useEffect(() => () => clearTimers(), [clearTimers]);

  useEffect(() => {
    guestTokenRef.current = loadGuestToken();
  }, []);

  const endRun = useCallback((s: Partial<RunState>, results: RushResults | null) => {
    dispatch({ type: 'RUN_OVER', state: s, results, clientNow: Date.now() });
  }, []);

  /** Ask the server (source of truth) whether the clock ran out; it ends the run lazily. */
  const pollTimeout = useCallback((runId: string) => {
    const attempt = (tries: number) => {
      const retry = () => {
        if (tries < TIMINGS.TIMEOUT_POLL_TRIES) later(TIMINGS.TIMEOUT_POLL, () => attempt(tries + 1));
      };
      rushApi.getRun(auth(), runId).then((summary) => {
        if (stateRef.current.runId !== runId) return;
        if (summary.run_over) endRun(summary, summary.results ?? null);
        else retry();
      }).catch(retry);
    };
    attempt(0);
  }, [auth, endRun, later]);

  const start = useCallback(async (mode: RushMode) => {
    clearTimers();
    genRef.current += 1;
    finishedRef.current = null;
    setShowResults(false);
    setGuestPb(false);
    setCountdown(null);
    saveLastMode(mode);
    dispatch({ type: 'START_REQUESTED', mode });

    const gen = genRef.current;
    try {
      const res = await rushApi.createRun({ ...auth(), guestToken: null }, mode);
      if (gen !== genRef.current) return;
      guestTokenRef.current = res.guest_token ?? null;
      saveGuestToken(guestTokenRef.current);
      const now = Date.now();
      dispatch({ type: 'RUN_CREATED', response: res, clientNow: now });

      // Align "Go!" with the server's started_at (create + 3 s), so the clock
      // starts exactly when the board becomes playable.
      const startedAt = Date.parse(res.started_at) - (Date.parse(res.server_now) - now);
      const toGo = Math.max(startedAt - now, 0);
      const firstStep = Math.max(toGo - 3 * TIMINGS.COUNTDOWN_STEP, 0);
      const goAt = Math.max(toGo, firstStep + 3 * TIMINGS.COUNTDOWN_STEP);
      later(firstStep, () => setCountdown(3));
      later(firstStep + TIMINGS.REVEAL_IN_THREE, () => dispatch({ type: 'PUZZLE_REVEALED' }));
      later(firstStep + TIMINGS.COUNTDOWN_STEP, () => setCountdown(2));
      later(firstStep + 2 * TIMINGS.COUNTDOWN_STEP, () => setCountdown(1));
      later(goAt, () => {
        setCountdown('go');
        dispatch({ type: 'SETUP_PLAYED' });
        play('move');
      });
      later(goAt + TIMINGS.GO_VISIBLE, () => setCountdown(null));
    } catch (e) {
      if (gen !== genRef.current) return;
      const code = e instanceof RushApiError ? e.code : 'network';
      dispatch({ type: 'START_FAILED', error: code });
    }
  }, [auth, clearTimers, later, play]);

  const playNextPuzzle = useCallback(() => {
    dispatch({ type: 'ADVANCE' });
    later(TIMINGS.BOARD_CLEAR, () => dispatch({ type: 'PUZZLE_REVEALED' }));
    later(TIMINGS.BOARD_CLEAR + TIMINGS.FADE_IN, () => {
      dispatch({ type: 'SETUP_PLAYED' });
      play('move');
    });
  }, [later, play]);

  const onMove = useCallback(async (from: Key, to: Key, promotion?: string) => {
    const s = stateRef.current;
    if (s.inputLocked || s.phase !== 'playing' || !s.runId) return;
    const uci = `${from}${to}${promotion ?? ''}`;
    const before = { fen: s.fen, lastMove: s.lastMove };
    const isCapture = /[a-z]/i.test(boardCharAt(s.fen, to));
    dispatch({ type: 'USER_MOVED', uci });
    play(isCapture ? 'capture' : 'move');

    const runId = s.runId;
    try {
      const res = await rushApi.move(auth(), runId, uci);
      if (stateRef.current.runId !== runId) return;
      dispatch({ type: 'MOVE_RESULT', response: res, clientNow: Date.now() });
      if (res.result === 'wrong') play('clank');
      else if (res.result === 'solved') play('success');

      if (res.run_over) return;
      if (res.result === 'correct') {
        later(TIMINGS.BADGE_HOLD_OK, () => {
          dispatch({ type: 'REPLY_PLAYED' });
          play('move');
        });
      } else {
        later(res.result === 'solved' ? TIMINGS.BADGE_HOLD_OK : TIMINGS.BADGE_HOLD_FAIL, playNextPuzzle);
      }
    } catch (e) {
      if (stateRef.current.runId !== runId) return;
      if (e instanceof RushApiError && e.code === 'run_over') {
        endRun(e.body as Partial<RunState>, (e.body.results as RushResults) ?? null);
        return;
      }
      dispatch({ type: 'MOVE_REJECTED', ...before });
    }
  }, [auth, endRun, later, play, playNextPuzzle]);

  const quit = useCallback(async () => {
    const runId = stateRef.current.runId;
    if (!runId || stateRef.current.phase === 'over') return;
    clearTimers();
    setCountdown(null);
    try {
      const res = await rushApi.quit(auth(), runId);
      endRun(res, res.results);
    } catch {
      endRun({ end_reason: 'quit' }, null);
    }
  }, [auth, clearTimers, endRun]);

  const reset = useCallback(() => {
    clearTimers();
    genRef.current += 1;
    setCountdown(null);
    setShowResults(false);
    dispatch({ type: 'RESET' });
  }, [clearTimers]);

  // Client-side deadline: lock and let the server confirm the timeout.
  useEffect(() => {
    if (state.phase !== 'playing' && state.phase !== 'countdown') return;
    if (state.deadlineMs === null || !state.runId) return;
    const runId = state.runId;
    const t = setTimeout(() => pollTimeout(runId), Math.max(state.deadlineMs - Date.now(), 0));
    return () => clearTimeout(t);
  }, [state.phase, state.deadlineMs, state.runId, pollTimeout]);

  // Run-over side effects, once per run.
  useEffect(() => {
    if (state.phase !== 'over' || !state.runId || finishedRef.current === state.runId) return;
    finishedRef.current = state.runId;
    clearTimers();
    // Guest bests live in localStorage (external store); the PB flag is its write result.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!isSignedIn) setGuestPb(recordGuestScore(state.mode, state.results?.score ?? state.score));
    saveGuestToken(null);
    later(TIMINGS.RESULTS_DELAY, () => setShowResults(true));
  }, [state.phase, state.runId, state.mode, state.results, state.score, isSignedIn, clearTimers, later]);

  // Coach toast auto-dismiss.
  useEffect(() => {
    if (!state.coach) return;
    const seq = state.coach.seq;
    const t = setTimeout(() => dispatch({ type: 'COACH_DISMISS', seq }), TIMINGS.COACH_VISIBLE);
    return () => clearTimeout(t);
  }, [state.coach]);

  const isPb = Boolean(state.results?.is_new_pb) || guestPb;

  return {
    state,
    countdown,
    showResults,
    setShowResults,
    isPb,
    isGuest: !isSignedIn,
    start,
    onMove,
    quit,
    reset,
    auth,
  };
}

/** Piece letter on `square` in a FEN ('' when empty). */
function boardCharAt(fen: string, square: string): string {
  const file = square.charCodeAt(0) - 97;
  const rank = 8 - Number(square[1]);
  const row = fen.split(' ')[0].split('/')[rank] ?? '';
  let col = 0;
  for (const ch of row) {
    if (/\d/.test(ch)) col += Number(ch);
    else {
      if (col === file) return ch;
      col += 1;
    }
    if (col > file) break;
  }
  return '';
}
