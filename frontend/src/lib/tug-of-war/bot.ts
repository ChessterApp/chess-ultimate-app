/**
 * "You vs Chesster" bot model for Tug of War — pure and deterministic given an
 * injected RNG, so every roll is unit-testable.
 *
 * The bot is the Chesster zebra at one of six static ranks, modelled on how a
 * person solves a puzzle:
 * - ONE "sees it" roll per attempt ({@link seeProbability}): a logistic curve on
 *   the rank's skill and its rating vs the puzzle's, minus a little per extra
 *   solution move. Seen → it plays the whole line. Not seen → it plays a
 *   plausible wrong move ({@link pickMissMove}), then re-rolls with an
 *   eliminated-idea bonus. Three wrongs skip, exactly as for a human.
 * - Human timing: a long first think scaled by difficulty (lognormal jitter,
 *   sometimes stuck), quick follow-up moves, impulsive wrong moves and a longer
 *   rethink after one.
 * The bot reports the same solved/wrong outcomes a human board does, so
 * scoring, rope, the 3-wrong skip and win rules are untouched.
 * {@link simulateBotPuzzle} replays the same model without timers; the
 * calibration test holds every rank to {@link BOT_CALIBRATION}.
 */

import { Chess, type Square } from 'chess.js';
import { MAX_WRONG_ATTEMPTS } from './gameReducer';
import type { TugPuzzle } from './types';

export type BotLevelId = 'baby' | 'junior' | 'club' | 'expert' | 'master' | 'grandmaster';

export interface BotLevel {
  id: BotLevelId;
  /** Puzzle-style rating; drives the "sees it" chance and the puzzles dealt. */
  rating: number;
  /** Base think time T for the first move of a puzzle at its own rating. */
  thinkSeconds: number;
  /** Rank badge colour (hex). Display name lives in i18n `tugOfWar.bot.levels.<id>`. */
  color: string;
}

export const BOT_LEVELS: BotLevel[] = [
  { id: 'baby', rating: 500, thinkSeconds: 12, color: '#34d399' },
  { id: 'junior', rating: 800, thinkSeconds: 9.5, color: '#38bdf8' },
  { id: 'club', rating: 1100, thinkSeconds: 7.2, color: '#a78bfa' },
  { id: 'expert', rating: 1400, thinkSeconds: 5.2, color: '#fbbf24' },
  { id: 'master', rating: 1700, thinkSeconds: 3.8, color: '#fb923c' },
  { id: 'grandmaster', rating: 2000, thinkSeconds: 2.4, color: '#f43f5e' },
];

/**
 * What each rank achieves on puzzles within ±150 of its own rating: solve rate
 * and average seconds per puzzle (misses and skips included). The setup cards
 * show these; the calibration test keeps the model honest to them.
 */
export const BOT_CALIBRATION: Record<BotLevelId, { solveRate: number; secondsPerPuzzle: number }> = {
  baby: { solveRate: 0.55, secondsPerPuzzle: 25 },
  junior: { solveRate: 0.65, secondsPerPuzzle: 20 },
  club: { solveRate: 0.72, secondsPerPuzzle: 16 },
  expert: { solveRate: 0.8, secondsPerPuzzle: 12 },
  master: { solveRate: 0.87, secondsPerPuzzle: 9 },
  grandmaster: { solveRate: 0.93, secondsPerPuzzle: 6 },
};

/** Bot matches end after this long; the rope leader wins (centre = draw). */
export const BOT_MATCH_MS = 5 * 60 * 1000;
/** Matches TugBoard's scripted-reply delay. */
export const BOT_REPLY_DELAY_MS = 300;
/** How long a wrong bot move stays on the board before snapping back. */
export const BOT_WRONG_SHOW_MS = 600;
/** No first-move think is ever shorter than this. */
export const MIN_DELAY_MS = 1500;

/** "Sees it" curve: logit = SKILL_BASE + SKILL_SLOPE·strength + (bot − puzzle)/RATING_SCALE − penalty. */
export const SKILL_BASE = -2.15;
export const SKILL_SLOPE = 2.9;
export const RATING_SCALE = 250;
/** Logit penalty per solution move beyond the first. */
export const MOVE_PENALTY = 0.25;
/** Each rejected idea closes this share of the remaining gap to certainty. */
export const RETRY_BONUS = 0.15;
/** Lognormal sigma of the first-move think. */
export const THINK_SIGMA = 0.3;
/** Chance a first think gets stuck, and the stretch it then takes. */
export const STUCK_CHANCE = 0.1;
export const STUCK_RANGE = [1.5, 2.5] as const;
/** Difficulty stretch of the first think is clamped to this range. */
export const DIFFICULTY_RANGE = [0.5, 2.5] as const;
/** Follow-up solution moves: 3 s for the weakest rank down to 1 s for the strongest. */
export const FOLLOW_UP_MS = [1000, 3000] as const;
/** Wrong moves come impulsively, then the rethink before a retry is longer (× T). */
export const WRONG_RANGE = [0.5, 0.8] as const;
export const RETHINK_RANGE = [1.0, 1.4] as const;

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
const between = ([lo, hi]: readonly [number, number], rng: () => number) => lo + (hi - lo) * rng();

export function botLevel(id: BotLevelId): BotLevel {
  return BOT_LEVELS.find((l) => l.id === id) ?? BOT_LEVELS[0];
}

/** 0 at the weakest rank's rating, 1 at the strongest (unclamped beyond). */
export function botStrength(rating: number): number {
  const lo = BOT_LEVELS[0].rating;
  const hi = BOT_LEVELS[BOT_LEVELS.length - 1].rating;
  return (rating - lo) / (hi - lo);
}

/** Base think time for any rating: interpolated between the ranks, clamped at the ends. */
export function thinkSecondsFor(rating: number): number {
  const first = BOT_LEVELS[0];
  const last = BOT_LEVELS[BOT_LEVELS.length - 1];
  if (rating <= first.rating) return first.thinkSeconds;
  if (rating >= last.rating) return last.thinkSeconds;
  const i = BOT_LEVELS.findIndex((l) => l.rating >= rating);
  const a = BOT_LEVELS[i - 1];
  const b = BOT_LEVELS[i];
  return a.thinkSeconds + ((rating - a.rating) / (b.rating - a.rating)) * (b.thinkSeconds - a.thinkSeconds);
}

/** Moves the solver plays in a solution line (even indices). */
export function botMoveCount(moves: string[]): number {
  return Math.ceil(moves.length / 2);
}

/**
 * Chance the bot sees the whole solution on this attempt. `retries` is how
 * many wrong ideas it has already rejected on this puzzle; each closes
 * {@link RETRY_BONUS} of the remaining gap.
 */
export function seeProbability(
  botRating: number,
  puzzleRating: number,
  botMoves: number,
  retries = 0,
): number {
  const logit =
    SKILL_BASE +
    SKILL_SLOPE * botStrength(botRating) +
    (botRating - puzzleRating) / RATING_SCALE -
    MOVE_PENALTY * Math.max(0, botMoves - 1);
  const p = 1 / (1 + Math.exp(-logit));
  return 1 - (1 - p) * (1 - RETRY_BONUS) ** retries;
}

/** One roll: true with the given probability. */
export function rollSolve(probability: number, rng: () => number = Math.random): boolean {
  return rng() < probability;
}

/** Standard normal via Box–Muller. */
function gaussian(rng: () => number): number {
  return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
}

/**
 * Think before the first move of a puzzle: T stretched by the puzzle's
 * difficulty for this bot, mean-one lognormal jitter, and a
 * {@link STUCK_CHANCE} of getting stuck.
 */
export function firstMoveDelayMs(level: BotLevel, puzzleRating: number, rng: () => number = Math.random): number {
  const difficulty = clamp(2 ** ((puzzleRating - level.rating) / 400), ...DIFFICULTY_RANGE);
  const jitter = Math.exp(THINK_SIGMA * gaussian(rng) - THINK_SIGMA ** 2 / 2);
  const stuck = rng() < STUCK_CHANCE ? between(STUCK_RANGE, rng) : 1;
  return Math.max(MIN_DELAY_MS, Math.round(level.thinkSeconds * 1000 * difficulty * jitter * stuck));
}

/** A follow-up solution move once the line is seen: 1–3 s, faster for stronger ranks. */
export function followUpDelayMs(level: BotLevel, rng: () => number = Math.random): number {
  const [lo, hi] = FOLLOW_UP_MS;
  const base = hi - (hi - lo) * clamp(botStrength(level.rating), 0, 1);
  return Math.round(clamp(base * (0.75 + 0.5 * rng()), lo, hi));
}

/** An impulsive wrong move: 0.5–0.8 × T. */
export function wrongMoveDelayMs(level: BotLevel, rng: () => number = Math.random): number {
  return Math.round(level.thinkSeconds * 1000 * between(WRONG_RANGE, rng));
}

/** The rethink before a correct retry: 1.0–1.4 × T. */
export function rethinkDelayMs(level: BotLevel, rng: () => number = Math.random): number {
  return Math.round(level.thinkSeconds * 1000 * between(RETHINK_RANGE, rng));
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

const PIECE_VALUE: Record<string, number> = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
/** Only the best few candidates are in the running for a miss. */
export const MISS_CANDIDATES = 4;

/**
 * A plausible wrong move for this ply: weighted-random among the top
 * {@link MISS_CANDIDATES} tempting ones — checks, captures (more so of a
 * bigger piece), the solution's piece or piece type, moves onto or eyeing the
 * solution's target square — and a quiet random move only when nothing
 * tempts. Never the solution, an alternative mate or one of `rejected`; null
 * when no such move is left (the bot can't miss).
 */
export function pickMissMove(
  fen: string,
  moves: string[],
  idx: number,
  rejected: readonly string[] = [],
  rng: () => number = Math.random,
): string | null {
  const chess = new Chess(fen);
  const solution = moves[idx]?.slice(0, 4) ?? '';
  const solFrom = solution.slice(0, 2) as Square;
  const solTo = solution.slice(2, 4) as Square;
  const solType = chess.get(solFrom)?.type;
  const seen = new Set<string>([solution, ...rejected]);
  const quiet: string[] = [];
  const scored: { uci: string; score: number }[] = [];
  for (const m of chess.moves({ verbose: true })) {
    const uci = `${m.from}${m.to}`;
    // Promotion variants share from+to; the board judges them as one move.
    if (seen.has(uci)) continue;
    seen.add(uci);
    chess.move({ from: m.from, to: m.to, promotion: 'q' });
    const mates = chess.isCheckmate();
    const check = chess.inCheck();
    const eyes = m.to !== solTo && chess.attackers(solTo, m.color).includes(m.to);
    chess.undo();
    if (mates) continue;
    let score = 0;
    if (check) score += 4;
    if (m.captured) score += 3 + (PIECE_VALUE[m.captured] > PIECE_VALUE[m.piece] ? 2 : 0);
    if (m.from === solFrom) score += 2;
    else if (m.piece === solType) score += 1;
    if (m.to === solTo) score += 2;
    if (eyes) score += 1;
    if (score > 0) scored.push({ uci, score });
    else quiet.push(uci);
  }
  if (scored.length === 0) return quiet.length ? quiet[Math.floor(rng() * quiet.length)] : null;
  const top = scored.sort((a, b) => b.score - a.score).slice(0, MISS_CANDIDATES);
  let r = rng() * top.reduce((sum, c) => sum + c.score, 0);
  for (const c of top) {
    r -= c.score;
    if (r < 0) return c.uci;
  }
  return top[top.length - 1].uci;
}

/** One attempt's plan: seen → the line after `delayMs`, otherwise a wrong move after it. */
export interface BotAttempt {
  seen: boolean;
  delayMs: number;
}

/**
 * Roll one attempt at a puzzle's first move. `retries` = wrong moves already
 * played on it; `canMiss` false (no wrong move left) forces a seen line.
 */
export function planAttempt(
  level: BotLevel,
  puzzle: Pick<TugPuzzle, 'moves' | 'rating'>,
  retries: number,
  canMiss: boolean,
  rng: () => number = Math.random,
): BotAttempt {
  const p = seeProbability(level.rating, puzzle.rating, botMoveCount(puzzle.moves), retries);
  const seen = !canMiss || rollSolve(p, rng);
  if (!seen) return { seen, delayMs: wrongMoveDelayMs(level, rng) };
  return {
    seen,
    delayMs: retries === 0 ? firstMoveDelayMs(level, puzzle.rating, rng) : rethinkDelayMs(level, rng),
  };
}

/**
 * The model without timers: how one puzzle goes for `level`, with the same
 * delays useTugBot schedules. `wrongCount` = how many wrong first moves exist
 * (each miss uses one up).
 */
export function simulateBotPuzzle(
  level: BotLevel,
  puzzle: Pick<TugPuzzle, 'fen' | 'moves' | 'rating'>,
  rng: () => number = Math.random,
  wrongCount: number = wrongMoves(puzzle.fen, puzzle.moves, 0).length,
): { solved: boolean; ms: number; misses: number } {
  let ms = 0;
  for (let misses = 0; misses < MAX_WRONG_ATTEMPTS; misses++) {
    const attempt = planAttempt(level, puzzle, misses, misses < wrongCount, rng);
    ms += attempt.delayMs;
    if (!attempt.seen) {
      // The third wrong skips straight to the next puzzle.
      if (misses < MAX_WRONG_ATTEMPTS - 1) ms += BOT_WRONG_SHOW_MS;
      continue;
    }
    for (let i = 1; i < botMoveCount(puzzle.moves); i++) {
      ms += BOT_REPLY_DELAY_MS + followUpDelayMs(level, rng);
    }
    return { solved: true, ms, misses };
  }
  return { solved: false, ms, misses: MAX_WRONG_ATTEMPTS };
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
