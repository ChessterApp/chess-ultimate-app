/**
 * useTugBot — the timer-driven controller that plays the bot's board.
 *
 * Kept apart from the pure reducer: it walks the current puzzle with its own
 * chess.js copy, waits a jittered think time per move, rolls each attempt via
 * {@link pickBotMove}, and reports the same `onSolved` / `onWrong` a human
 * board does. Scripted opponent replies follow the human board's flow. The
 * level may change mid-puzzle (Adaptive mode moves rating/speed after every
 * rope swing): each think and roll reads the latest one. The
 * pending timer pauses while the tab is hidden or the bot is inactive (match
 * over), and is cancelled on unmount.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import type { TugPuzzle } from './types';
import {
  botDelayMs,
  pickBotMove,
  solveProbability,
  PausableTimer,
  type BotLevel,
} from './bot';

/** Matches TugBoard's scripted-reply delay. */
export const BOT_REPLY_DELAY_MS = 300;
/** How long a wrong bot move stays on the board before snapping back. */
export const BOT_WRONG_SHOW_MS = 600;

export interface BotView {
  fen: string;
  lastMove?: [string, string];
  /** True while the bot is "thinking" about its next move. */
  thinking: boolean;
}

interface UseTugBotOptions {
  /** Null when not in bot mode (the hook stays idle). Fixed (static) or changing (adaptive). */
  level: BotLevel | null;
  puzzle: TugPuzzle | null;
  /** Board pointer; a change means a fresh puzzle even if the id repeats. */
  round: number;
  /** False once the match is over. */
  active: boolean;
  onSolved: () => void;
  onWrong: () => void;
  rng?: () => number;
}

const toMove = (uci: string) => ({
  from: uci.slice(0, 2),
  to: uci.slice(2, 4),
  promotion: uci.length > 4 ? uci[4] : 'q',
});

export function useTugBot({
  level,
  puzzle,
  round,
  active,
  onSolved,
  onWrong,
  rng = Math.random,
}: UseTugBotOptions): BotView {
  const [view, setView] = useState<BotView>({ fen: puzzle?.fen ?? '', thinking: false });
  const timerRef = useRef<PausableTimer | null>(null);
  timerRef.current ??= new PausableTimer(true);
  // Latest props for timer callbacks scheduled under older renders.
  const latest = useRef({ level, puzzle, onSolved, onWrong, rng });
  latest.current = { level, puzzle, onSolved, onWrong, rng };

  // (Re)start on every new puzzle: reset the position and think about move 1.
  useEffect(() => {
    const timer = timerRef.current!;
    timer.cancel();
    if (!level || !puzzle) return;
    const chess = new Chess(puzzle.fen);
    let idx = 0;

    const show = (thinking: boolean) => {
      const last = chess.history({ verbose: true }).at(-1);
      setView({ fen: chess.fen(), lastMove: last && [last.from, last.to], thinking });
    };

    const think = () => {
      show(true);
      const { level: now, rng: roll } = latest.current;
      timer.schedule(attempt, botDelayMs(now ?? level, roll));
    };

    const attempt = () => {
      const { level: now, rng: roll, onSolved: solved, onWrong: wrong } = latest.current;
      const p = solveProbability((now ?? level).rating, puzzle.rating);
      const pick = pickBotMove(chess.fen(), puzzle.moves, idx, p, roll);

      if (!pick.correct) {
        // Show the wrong move briefly, then snap back and think again. A third
        // miss makes the reducer skip the puzzle, which restarts this effect.
        const probe = new Chess(chess.fen());
        probe.move(toMove(pick.uci));
        setView({ fen: probe.fen(), lastMove: [pick.uci.slice(0, 2), pick.uci.slice(2, 4)], thinking: false });
        wrong();
        timer.schedule(think, BOT_WRONG_SHOW_MS);
        return;
      }

      chess.move(toMove(pick.uci));
      idx += 1;
      if (idx >= puzzle.moves.length || chess.isCheckmate()) {
        show(false);
        solved();
        return;
      }
      show(false);
      timer.schedule(() => {
        chess.move(toMove(puzzle.moves[idx]));
        idx += 1;
        if (idx >= puzzle.moves.length) {
          show(false);
          latest.current.onSolved();
        } else {
          think();
        }
      }, BOT_REPLY_DELAY_MS);
    };

    think();
    return () => timer.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [!!level, puzzle?.id, round]);

  // Pause while inactive or the tab is hidden; resume where it left off.
  useEffect(() => {
    const timer = timerRef.current!;
    const sync = () => {
      if (active && !document.hidden) timer.resume();
      else timer.pause();
    };
    sync();
    document.addEventListener('visibilitychange', sync);
    return () => document.removeEventListener('visibilitychange', sync);
  }, [active]);

  useEffect(() => () => timerRef.current?.cancel(), []);

  return view;
}
