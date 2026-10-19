/**
 * "You vs Chesster" bot model for Tug of War — pure and deterministic given an
 * injected RNG, so every roll is unit-testable.
 *
 * The bot is the Chesster zebra at one of six static ranks. Per puzzle move it
 * waits ~secondsPerMove (±25% jitter), then rolls against an Elo expected score
 * of its rating vs the puzzle's: a hit plays the scripted solution move, a miss
 * plays a random legal move the board would reject as wrong. The bot reports
 * the same solved/wrong outcomes a human board does, so scoring, rope, the
 * 3-wrong skip and win rules are untouched.
 */

import { Chess } from 'chess.js';
import { TUG_LEVELS, type TugLevel } from './prefetch';

export type BotLevelId = 'baby' | 'junior' | 'club' | 'expert' | 'master' | 'grandmaster';

export interface BotLevel {
  id: BotLevelId;
  /** Puzzle-style rating; drives solve probability and the puzzle band. */
  rating: number;
  /** Mean thinking time per bot move. */
  secondsPerMove: number;
  /** Rank badge colour (hex). Display name lives in i18n `tugOfWar.bot.levels.<id>`. */
  color: string;
}

export const BOT_LEVELS: BotLevel[] = [
  { id: 'baby', rating: 500, secondsPerMove: 14, color: '#34d399' },
  { id: 'junior', rating: 800, secondsPerMove: 12, color: '#38bdf8' },
  { id: 'club', rating: 1100, secondsPerMove: 10, color: '#a78bfa' },
  { id: 'expert', rating: 1400, secondsPerMove: 8, color: '#fbbf24' },
  { id: 'master', rating: 1700, secondsPerMove: 6, color: '#fb923c' },
  { id: 'grandmaster', rating: 2000, secondsPerMove: 4, color: '#f43f5e' },
];

/** Bot matches end after this long; the rope leader wins (centre = draw). */
export const BOT_MATCH_MS = 5 * 60 * 1000;
/** Fraction of secondsPerMove each delay may vary by. */
export const DELAY_JITTER = 0.25;
/** No bot move ever comes faster than this. */
export const MIN_DELAY_MS = 1500;

export function botLevel(id: BotLevelId): BotLevel {
  return BOT_LEVELS.find((l) => l.id === id) ?? BOT_LEVELS[0];
}

/** Elo expected score: the chance a `botRating` player solves a `puzzleRating` move. */
export function solveProbability(botRating: number, puzzleRating: number): number {
  return 1 / (1 + 10 ** ((puzzleRating - botRating) / 400));
}

/** Thinking delay for one bot move: secondsPerMove ±25%, never under 1.5s. */
export function botDelayMs(level: BotLevel, rng: () => number = Math.random): number {
  const jitter = 1 + (rng() * 2 - 1) * DELAY_JITTER;
  return Math.max(MIN_DELAY_MS, Math.round(level.secondsPerMove * 1000 * jitter));
}

/** The puzzle band both sides draw from: the one containing the bot's rating. */
export function botPuzzleLevel(level: BotLevel): TugLevel {
  let band = TUG_LEVELS[0];
  for (const l of TUG_LEVELS) if (l.ratingFrom <= level.rating) band = l;
  return band.id;
}

/**
 * Every legal move (UCI, from+to) the board would reject at this ply — neither
 * the scripted move nor an alternative mate. Mirrors validateMove's
 * acceptance rule on one chess.js instance (move/undo) so a miss stays cheap.
 */
export function wrongMoves(fen: string, moves: string[], idx: number): string[] {
  const chess = new Chess(fen);
  const expected = moves[idx]?.slice(0, 4);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const m of chess.moves({ verbose: true })) {
    const uci = `${m.from}${m.to}`;
    // Promotion variants share from+to; the board judges them as one move.
    if (uci === expected || seen.has(uci)) continue;
    seen.add(uci);
    chess.move({ from: m.from, to: m.to, promotion: 'q' });
    const mates = chess.isCheckmate();
    chess.undo();
    if (!mates) out.push(uci);
  }
  return out;
}

/** One attempt's roll: true (solve) with the given probability. */
export function rollSolve(probability: number, rng: () => number = Math.random): boolean {
  return rng() < probability;
}

/** One bot attempt: the scripted move on a hit, a random wrong legal move on a miss. */
export function pickBotMove(
  fen: string,
  moves: string[],
  idx: number,
  probability: number,
  rng: () => number = Math.random,
): { uci: string; correct: boolean } {
  const expected = moves[idx];
  if (rollSolve(probability, rng)) return { uci: expected, correct: true };
  const wrong = wrongMoves(fen, moves, idx);
  // Only accepted moves exist (e.g. a single legal reply): the bot can't miss.
  if (wrong.length === 0) return { uci: expected, correct: true };
  return { uci: wrong[Math.floor(rng() * wrong.length)], correct: false };
}

/**
 * A setTimeout that can be paused and resumed, keeping its remaining time.
 * Holds at most one pending callback; scheduling replaces it.
 */
export class PausableTimer {
  private handle: ReturnType<typeof setTimeout> | null = null;
  private fn: (() => void) | null = null;
  private remaining = 0;
  private startedAt = 0;

  constructor(private paused = false) {}

  schedule(fn: () => void, ms: number) {
    this.cancel();
    this.fn = fn;
    this.remaining = ms;
    if (!this.paused) this.start();
  }

  pause() {
    if (this.paused) return;
    this.paused = true;
    if (this.handle) {
      clearTimeout(this.handle);
      this.handle = null;
      this.remaining -= Date.now() - this.startedAt;
    }
  }

  resume() {
    if (!this.paused) return;
    this.paused = false;
    if (this.fn) this.start();
  }

  cancel() {
    if (this.handle) clearTimeout(this.handle);
    this.handle = null;
    this.fn = null;
  }

  private start() {
    this.startedAt = Date.now();
    this.handle = setTimeout(() => {
      this.handle = null;
      const fn = this.fn;
      this.fn = null;
      fn?.();
    }, Math.max(0, this.remaining));
  }
}
