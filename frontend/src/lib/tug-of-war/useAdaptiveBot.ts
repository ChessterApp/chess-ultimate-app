/**
 * useAdaptiveBot — runs the adaptive model (adaptive.ts) alongside a You vs
 * Chesster match. It watches the game state the reducer produces: a human
 * solve or skip scores the player and moves the bot ladder, a bot solve drops
 * it, and a 20 s creep (visible tab, live match only) keeps nudging it up. When
 * the match ends the result is persisted once, so a rematch starts near the
 * player's level.
 *
 * Idle (returns null) until given a session; a new session object = a new match.
 */

'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { currentPuzzle, type GameState } from './gameReducer';
import {
  adaptiveReducer,
  initialAdaptive,
  ladderBotLevel,
  saveAdaptive,
  targetRating,
  toSaved,
  CREEP_EVERY_MS,
  type AdaptiveEvent,
  type AdaptiveState,
  type SavedAdaptive,
} from './adaptive';
import type { BotLevel } from './bot';

export interface AdaptiveSession {
  /** The saved result this match starts from (null = first match). */
  saved: SavedAdaptive | null;
}

export interface AdaptiveView {
  state: AdaptiveState;
  /** What useTugBot plays: the ladder's rating/speed under the nearest rank. */
  bot: BotLevel;
  /** Rating the next puzzle batch is drawn around. */
  target: number;
  /** Set (and persisted) once the match is over. */
  result: SavedAdaptive | null;
}

interface Tracked {
  session: AdaptiveSession;
  state: AdaptiveState;
  result: SavedAdaptive | null;
}

interface Options {
  /** Monotonic ms clock for solve times. */
  clock?: () => number;
  /** Wall clock for the saved date. */
  now?: () => Date;
  save?: (saved: SavedAdaptive) => void;
}

export function useAdaptiveBot(
  session: AdaptiveSession | null,
  game: GameState,
  { clock = Date.now, now = () => new Date(), save = saveAdaptive }: Options = {},
): AdaptiveView | null {
  const [tracked, setTracked] = useState<Tracked | null>(null);
  // New session → fresh model (adjusting state while rendering, React's
  // documented alternative to a reset effect).
  if (session && tracked?.session !== session) {
    setTracked({ session, state: initialAdaptive(session.saved), result: null });
  }
  const current = tracked && tracked.session === session ? tracked : null;

  const prev = useRef<{ session: AdaptiveSession | null; game: GameState }>({ session: null, game });
  const shownAt = useRef(0);
  const opts = useRef({ clock, now, save });
  opts.current = { clock, now, save };

  useEffect(() => {
    if (!current || current.result) return;
    const p = prev.current;
    prev.current = { session: current.session, game };
    if (p.session !== current.session) {
      shownAt.current = opts.current.clock();
      return;
    }
    if (p.game === game || p.game.phase !== 'match') return;

    const events: AdaptiveEvent[] = [];
    const before = p.game.boardA;
    const rating = currentPuzzle(before)?.rating ?? current.state.player.estimate;
    if (game.boardA.solved > before.solved) {
      const seconds = (opts.current.clock() - shownAt.current) / 1000;
      events.push({ type: 'HUMAN_SOLVED', puzzleRating: rating, seconds });
    }
    if (game.boardA.skips > before.skips) events.push({ type: 'HUMAN_SKIPPED', puzzleRating: rating });
    if (game.boardB.solved > p.game.boardB.solved) events.push({ type: 'BOT_SOLVED' });
    if (game.boardA.index !== before.index) shownAt.current = opts.current.clock();

    const state = events.reduce(adaptiveReducer, current.state);
    let result: SavedAdaptive | null = null;
    if (game.phase === 'over') {
      result = toSaved(state, opts.current.now);
      opts.current.save(result);
    }
    if (state !== current.state || result) {
      setTracked({ ...current, state, result });
    }
  }, [current, game]);

  const live = !!current && !current.result && game.phase === 'match';
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => {
      if (document.hidden) return;
      setTracked((t) => t && { ...t, state: adaptiveReducer(t.state, { type: 'CREEP' }) });
    }, CREEP_EVERY_MS);
    return () => clearInterval(id);
  }, [live]);

  return useMemo(
    () =>
      current && {
        state: current.state,
        bot: ladderBotLevel(current.state.ladder),
        target: targetRating(current.state),
        result: current.result,
      },
    [current],
  );
}
