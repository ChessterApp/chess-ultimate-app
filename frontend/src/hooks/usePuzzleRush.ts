'use client';

/**
 * usePuzzleRush — drives one Puzzle Rush run on top of the pure `runReducer`:
 * pack prefetch / top-up, the 3-2-1-Go! countdown, the §3 feedback/transition
 * timings, the local clock, sounds, and the single background `/runs/finish`
 * for signed-in players (with a localStorage outbox). No network call sits
 * between a move and its ✓/✕: the reducer judges the move in the same update.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import type { Key } from 'chessground/types';
import { rushApi, type RushAuth } from '@/lib/puzzle-rush/api';
import { dequeueFinish, enqueueFinish, flushOutbox } from '@/lib/puzzle-rush/outbox';
import { newRunId, newSeed, retryDelay, topUpFrom } from '@/lib/puzzle-rush/pack';
import { finishRequest, initialRunState, resultTiles, reviewAttempts, runReducer, type MoveOutcome } from '@/lib/puzzle-rush/runReducer';
import { applyGuestScore, loadGuestBests, localStore, recordGuestScore, saveLastMode } from '@/lib/puzzle-rush/storage';
import type { ModeBests, RushMode, RushPuzzle } from '@/lib/puzzle-rush/types';
import { useSoundEffects } from '@/hooks/useSoundEffects';

// §3 implementation targets.
export const TIMINGS = {
  COUNTDOWN_LEAD_IN: 750,
  COUNTDOWN_STEP: 750,
  GO_VISIBLE: 1100,
  BADGE_HOLD_OK: 160,
  BADGE_HOLD_FAIL: 240,
  BOARD_CLEAR: 150,
  FADE_IN: 170,
  REVEAL_IN_THREE: 200,
  COACH_VISIBLE: 2600,
} as const;

export type CountdownStep = 3 | 2 | 1 | 'go' | null;

const now = () => performance.now();

interface PendingPack {
  seed: string;
  promise: Promise<RushPuzzle[]>;
}

function fetchPack(): PendingPack {
  const seed = newSeed();
  const promise = rushApi.pack(seed).then((r) => r.puzzles);
  promise.catch(() => {}); // awaited (and handled) by start()
  return { seed, promise };
}

export function usePuzzleRush(initialMode: RushMode) {
  const { getToken, isSignedIn, userId } = useAuth();
  const { play } = useSoundEffects();
  const [state, dispatch] = useReducer(runReducer, initialMode, initialRunState);
  const [countdown, setCountdown] = useState<CountdownStep>(null);
  const [resultsClosed, setResultsClosed] = useState(false);
  // Guest bests as they were when the run started (the results derive from them).
  const [guestBefore, setGuestBefore] = useState<Record<RushMode, ModeBests> | null>(null);
  // Run id once it is recorded (server for signed-in, localStorage for guests).
  const [recordedRun, setRecordedRun] = useState<string | null>(null);
  const [finishFailed, setFinishFailed] = useState(false);

  const stateRef = useRef(state);
  useLayoutEffect(() => {
    stateRef.current = state;
  });
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  // Bumped per run so late timers / responses from an old run are ignored.
  const genRef = useRef(0);
  const finishedRef = useRef<string | null>(null);
  const nextPackRef = useRef<PendingPack | null>(null);
  const topUpRef = useRef(false);
  const outcomeRef = useRef<MoveOutcome | null>(null);

  // Stable identity: Clerk's getToken may change per render.
  const clerkRef = useRef({ getToken, isSignedIn });
  useLayoutEffect(() => {
    clerkRef.current = { getToken, isSignedIn };
  });
  const auth = useCallback((): RushAuth => ({
    getToken: async () => (clerkRef.current.isSignedIn ? clerkRef.current.getToken() : null),
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

  // Prefetch the first pack while the mode select is on screen.
  useEffect(() => {
    if (!nextPackRef.current) nextPackRef.current = fetchPack();
  }, []);

  // Resend runs whose /finish never landed (previous page loads).
  useEffect(() => {
    if (!isSignedIn || !userId) return;
    void flushOutbox(localStore(), userId, (body) => rushApi.finish(auth(), body));
  }, [isSignedIn, userId, auth]);

  const start = useCallback(async (mode: RushMode) => {
    clearTimers();
    genRef.current += 1;
    const gen = genRef.current;
    finishedRef.current = null;
    topUpRef.current = false;
    setResultsClosed(false);
    setGuestBefore(loadGuestBests());
    setFinishFailed(false);
    setCountdown(null);
    saveLastMode(mode);
    dispatch({ type: 'START_REQUESTED', mode });

    let pack = nextPackRef.current ?? fetchPack();
    let puzzles: RushPuzzle[] | null = null;
    for (let tries = 0; tries < 2 && !puzzles; tries += 1) {
      try {
        puzzles = await pack.promise;
      } catch {
        if (tries === 0) pack = fetchPack();
      }
    }
    if (gen !== genRef.current) return;
    if (!puzzles?.length) {
      nextPackRef.current = null;
      dispatch({ type: 'START_FAILED', error: 'network' });
      return;
    }
    dispatch({ type: 'RUN_STARTED', runId: newRunId(), seed: pack.seed, puzzles });
    // Play Again's pack, fetched during the countdown (never mid-run).
    nextPackRef.current = fetchPack();

    const step = TIMINGS.COUNTDOWN_STEP;
    const t0 = TIMINGS.COUNTDOWN_LEAD_IN;
    later(t0, () => setCountdown(3));
    later(t0 + TIMINGS.REVEAL_IN_THREE, () => dispatch({ type: 'PUZZLE_REVEALED' }));
    later(t0 + step, () => setCountdown(2));
    later(t0 + 2 * step, () => setCountdown(1));
    later(t0 + 3 * step, () => {
      setCountdown('go');
      dispatch({ type: 'GO', now: now(), wallNow: Date.now() });
      play('move');
    });
    later(t0 + 3 * step + TIMINGS.GO_VISIBLE, () => setCountdown(null));
  }, [clearTimers, later, play]);

  const onMove = useCallback((from: Key, to: Key, promotion?: string) => {
    dispatch({ type: 'USER_MOVED', uci: `${from}${to}${promotion ?? ''}`, now: now() });
  }, []);

  // Feedback pipeline after each judged move: sounds, then the reply or the next puzzle.
  useEffect(() => {
    const o = state.outcome;
    if (!o || outcomeRef.current === o) return;
    outcomeRef.current = o;
    play(o.capture ? 'capture' : 'move');
    if (o.result === 'wrong') play('clank');
    else if (o.result === 'solved') play('success');
    if (state.phase === 'over') return;
    if (o.result === 'correct') {
      later(TIMINGS.BADGE_HOLD_OK, () => {
        dispatch({ type: 'REPLY_PLAYED' });
        play('move');
      });
    } else {
      later(o.result === 'solved' ? TIMINGS.BADGE_HOLD_OK : TIMINGS.BADGE_HOLD_FAIL, () => dispatch({ type: 'ADVANCE' }));
    }
  }, [state.outcome, state.phase, later, play]);

  // A puzzle mounted mid-run (after ADVANCE or a stalled top-up): fade in, then the setup move.
  const midRunMount = state.phase === 'playing' && state.covered ? state.boardKey : null;
  useEffect(() => {
    if (midRunMount === null) return;
    later(TIMINGS.BOARD_CLEAR, () => dispatch({ type: 'PUZZLE_REVEALED' }));
    later(TIMINGS.BOARD_CLEAR + TIMINGS.FADE_IN, () => {
      dispatch({ type: 'SETUP_PLAYED' });
      play('move');
    });
  }, [midRunMount, later, play]);

  // Pack top-up: background, silent retries; the board only waits if the pack runs dry.
  const topUpAt = (state.phase === 'playing' || state.phase === 'countdown') && state.puzzle
    ? topUpFrom(state.pack.length, state.puzzle.index) : null;
  const seed = state.seed;
  useEffect(() => {
    if (topUpAt === null || !seed || topUpRef.current) return;
    topUpRef.current = true;
    const gen = genRef.current;
    const attempt = (failures: number) => {
      rushApi.pack(seed, topUpAt).then((r) => {
        if (gen !== genRef.current) return;
        topUpRef.current = false;
        dispatch({ type: 'PACK_EXTENDED', puzzles: r.puzzles });
      }).catch(() => {
        if (gen === genRef.current) later(retryDelay(failures), () => attempt(failures + 1));
      });
    };
    attempt(0);
  }, [topUpAt, seed, later]);

  // Local clock: timed modes end exactly at the deadline.
  useEffect(() => {
    if (state.phase !== 'playing' || state.deadlineMs === null) return;
    const deadline = state.deadlineMs;
    let t: ReturnType<typeof setTimeout>;
    const check = () => {
      const n = now();
      if (n >= deadline) dispatch({ type: 'TIME_UP', now: n });
      else t = setTimeout(check, deadline - n);
    };
    t = setTimeout(check, deadline - now());
    return () => clearTimeout(t);
  }, [state.phase, state.deadlineMs]);

  const quit = useCallback(() => {
    if (stateRef.current.phase !== 'playing') return;
    dispatch({ type: 'QUIT', now: now() });
  }, []);

  const reset = useCallback(() => {
    clearTimers();
    genRef.current += 1;
    setCountdown(null);
    dispatch({ type: 'RESET' });
  }, [clearTimers]);

  // Run over, once per run, after paint: the results modal has already
  // rendered from local state in the run-ending frame (no state is set here
  // before paint). Guests: persist the bests. Signed-in: queue + send /finish;
  // ranks / PB merge in when it returns.
  useEffect(() => {
    if (state.phase !== 'over' || !state.runId || finishedRef.current === state.runId) return;
    const runId = state.runId;
    finishedRef.current = runId;
    clearTimers();
    /* eslint-disable react-hooks/set-state-in-effect -- run-over sync with localStorage */
    setCountdown(null);
    if (!isSignedIn) {
      recordGuestScore(state.mode, state.score);
      setRecordedRun(runId);
      return;
    }
    /* eslint-enable react-hooks/set-state-in-effect */
    const body = finishRequest(state);
    if (!body || !userId) return;
    const store = localStore();
    enqueueFinish(store, userId, body);
    rushApi.finish(auth(), body).then((res) => {
      dequeueFinish(store, runId);
      if (stateRef.current.runId !== runId) return;
      dispatch({ type: 'FINISH_RESULT', results: res });
      setRecordedRun(runId);
    }).catch(() => {
      if (stateRef.current.runId === runId) setFinishFailed(true);
    });
  }, [state, isSignedIn, userId, auth, clearTimers]);

  // Coach toast auto-dismiss.
  useEffect(() => {
    if (!state.coach) return;
    const seq = state.coach.seq;
    const t = setTimeout(() => dispatch({ type: 'COACH_DISMISS', seq }), TIMINGS.COACH_VISIBLE);
    return () => clearTimeout(t);
  }, [state.coach]);

  const isGuest = !isSignedIn;
  const over = state.phase === 'over';
  const closeResults = useCallback(() => setResultsClosed(true), []);
  // Stable while the finished run sits still: Retry mode derives its board from these.
  const review = useMemo(() => (over ? reviewAttempts(state) : []), [over, state]);
  const guestResult = isGuest && over && guestBefore ? applyGuestScore(guestBefore[state.mode], state.score) : null;

  return {
    state,
    tiles: resultTiles(state),
    review,
    countdown,
    showResults: over && !resultsClosed,
    closeResults,
    isPb: isGuest ? Boolean(guestResult?.isPb) : Boolean(state.results?.is_new_pb),
    isGuest,
    /** Guests: this mode's on-device bests including the finished run. */
    guestBest: guestResult?.best ?? null,
    /** Signed-in: /runs/finish hasn't answered yet. */
    ranksPending: !isGuest && over && recordedRun !== state.runId && !finishFailed,
    /** The finished run is on the server (signed-in) / on the device (guest). */
    recorded: over && recordedRun === state.runId,
    start,
    onMove,
    quit,
    reset,
    auth,
  };
}
