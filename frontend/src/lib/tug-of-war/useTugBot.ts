/**
 * useTugBot — the timer-driven controller that plays the bot's board.
 *
 * Kept apart from the pure reducer: it walks the current puzzle with its own
 * chess.js copy and plays the bot model in bot.ts — one "sees it" roll per
 * attempt ({@link planAttempt}): seen → the whole line (quick follow-ups
 * after a long first think), not seen → a quick plausible wrong move
 * ({@link pickMissMove}, never repeated), then a retry with better odds. It
 * reports the same `onSolved` / `onWrong` a human board does. Scripted
 * opponent replies follow the human board's flow. The level may change
 * mid-puzzle (Adaptive mode moves the rating after every rope swing): each
 * roll and delay reads the latest one. The pending timer pauses while the tab
 * is hidden or the bot is inactive (match over), and is cancelled on unmount.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { Chess } from 'chess.js';
import type { TugPuzzle } from './types';
import {
  followUpDelayMs,
  pickMissMove,
  planAttempt,
  wrongMoves,
  PausableTimer,
  BOT_REPLY_DELAY_MS,
  BOT_WRONG_SHOW_MS,
  type BotLevel,
} from './bot';

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

    // Wrong first moves already played on this puzzle (each miss is a new idea).
    const rejected: string[] = [];
    const wrongCount = wrongMoves(puzzle.fen, puzzle.moves, 0).length;

    /** Roll an attempt at the first move: the line once seen, else a wrong move. */
    const attempt = () => {
      const { level: now, rng: roll } = latest.current;
      const plan = planAttempt(now ?? level, puzzle, rejected.length, rejected.length < wrongCount, roll);
      const miss = plan.seen ? null : pickMissMove(chess.fen(), puzzle.moves, idx, rejected, roll);
      show(true);
      timer.schedule(() => (miss ? playWrong(miss) : playLine()), plan.delayMs);
    };

    const playWrong = (uci: string) => {
      // Show the wrong move briefly, then snap back and rethink. A third miss
      // makes the reducer skip the puzzle, which restarts this effect.
      const probe = new Chess(chess.fen());
      probe.move(toMove(uci));
      setView({ fen: probe.fen(), lastMove: [uci.slice(0, 2), uci.slice(2, 4)], thinking: false });
      rejected.push(uci);
      latest.current.onWrong();
      timer.schedule(attempt, BOT_WRONG_SHOW_MS);
    };

    /** Play the next solution move; after the reply, a quick follow-up. */
    const playLine = () => {
      chess.move(toMove(puzzle.moves[idx]));
      idx += 1;
      if (idx >= puzzle.moves.length || chess.isCheckmate()) {
        show(false);
        latest.current.onSolved();
        return;
      }
      show(false);
      timer.schedule(() => {
        chess.move(toMove(puzzle.moves[idx]));
        idx += 1;
        if (idx >= puzzle.moves.length) {
          show(false);
          latest.current.onSolved();
          return;
        }
        show(true);
        const { level: now, rng: roll } = latest.current;
        timer.schedule(playLine, followUpDelayMs(now ?? level, roll));
      }, BOT_REPLY_DELAY_MS);
    };

    attempt();
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
