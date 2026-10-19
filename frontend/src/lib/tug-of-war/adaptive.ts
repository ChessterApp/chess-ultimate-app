/**
 * Adaptive ("Find my level") model for You vs Chesster — pure and
 * deterministic; the clock and storage are injected so every rule is
 * unit-testable.
 *
 * Two numbers move during a match:
 * - the PLAYER estimate: Elo-style, scored 1 for a solved puzzle and 0 for a
 *   skip (3 wrongs), with K decaying from 64 to 24 as more puzzles are seen,
 *   plus an EMA of seconds per solve;
 * - the BOT ladder: a continuous rating + seconds per move. It starts 300 below
 *   the player and slow, climbs a step (+100, −1 s) each time the human gains
 *   rope ground, drops half a step when the human loses ground, and creeps up
 *   a quarter step every 20 s so the match always resolves.
 * The zebra badge shows the nearest of the six static ranks.
 */

import { BOT_LEVELS, type BotLevel, type BotLevelId } from './bot';

export const START_RATING = 1000;
export const RATING_MIN = 400;
export const RATING_MAX = 2800;
export const K_START = 64;
export const K_MIN = 24;
/** Per-puzzle K decay factor towards K_MIN. */
export const K_DECAY = 0.85;
/** A saved estimate is trusted as if this many puzzles were already seen. */
export const RESUME_SEEN = 8;
/** EMA weight of the newest solve time. */
export const SPEED_ALPHA = 0.3;

/** The bot starts this far below the player estimate. */
export const BOT_HEADSTART = 300;
export const BOT_START_SECONDS = 14;
export const BOT_MIN_SECONDS = 3;
export const STEP_RATING = 100;
export const STEP_SECONDS = 1;
/** Losing ground moves the bot down this fraction of a step. */
export const DOWN_STEP = 0.5;
export const CREEP_EVERY_MS = 20_000;
/** +25 rating per creep. */
export const CREEP_STEP = 0.25;
/** Puzzle target = this share of the bot rating, the rest the player estimate. */
export const TARGET_BOT_WEIGHT = 0.6;

export const STORAGE_KEY = 'tug.adaptive.v1';

export interface PlayerModel {
  estimate: number;
  /** Puzzles scored so far (drives K). */
  seen: number;
  /** EMA seconds per solve; null before the first solve. */
  avgSeconds: number | null;
}

export interface BotLadder {
  rating: number;
  secondsPerMove: number;
}

export interface AdaptiveState {
  player: PlayerModel;
  ladder: BotLadder;
  /** Highest bot rating the human gained ground against; null until then. */
  peakBeaten: number | null;
  /** Direction of the last rank change on the badge. */
  trend: 'up' | 'down' | null;
}

export type AdaptiveEvent =
  | { type: 'HUMAN_SOLVED'; puzzleRating: number; seconds: number }
  | { type: 'HUMAN_SKIPPED'; puzzleRating: number }
  /** The bot solved a puzzle: the human lost rope ground. */
  | { type: 'BOT_SOLVED' }
  | { type: 'CREEP' };

export interface SavedAdaptive {
  estimate: number;
  avgSeconds: number | null;
  peakBotLevel: BotLevelId | null;
  /** ISO timestamp of the match end. */
  date: string;
}

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

export function kFactor(seen: number): number {
  return K_MIN + (K_START - K_MIN) * K_DECAY ** seen;
}

/** Elo expected score of a `rating` player on a `puzzleRating` puzzle. */
export function expectedScore(rating: number, puzzleRating: number): number {
  return 1 / (1 + 10 ** ((puzzleRating - rating) / 400));
}

export function initialPlayer(saved: SavedAdaptive | null = null): PlayerModel {
  if (!saved) return { estimate: START_RATING, seen: 0, avgSeconds: null };
  return { estimate: saved.estimate, seen: RESUME_SEEN, avgSeconds: saved.avgSeconds };
}

/** Score one puzzle (solved = 1, skipped = 0); a solve also feeds the speed EMA. */
export function updatePlayer(
  player: PlayerModel,
  puzzleRating: number,
  solved: boolean,
  seconds?: number,
): PlayerModel {
  const delta = kFactor(player.seen) * ((solved ? 1 : 0) - expectedScore(player.estimate, puzzleRating));
  let avgSeconds = player.avgSeconds;
  if (solved && seconds !== undefined) {
    avgSeconds = avgSeconds === null ? seconds : avgSeconds + SPEED_ALPHA * (seconds - avgSeconds);
  }
  return {
    estimate: clamp(player.estimate + delta, RATING_MIN, RATING_MAX),
    seen: player.seen + 1,
    avgSeconds,
  };
}

export function initialLadder(estimate: number): BotLadder {
  return { rating: Math.max(RATING_MIN, estimate - BOT_HEADSTART), secondsPerMove: BOT_START_SECONDS };
}

/** Move the bot `steps` rungs (negative = easier): ±100 rating, ∓1 s per move. */
export function stepLadder(ladder: BotLadder, steps: number): BotLadder {
  return {
    rating: clamp(ladder.rating + steps * STEP_RATING, RATING_MIN, RATING_MAX),
    secondsPerMove: clamp(ladder.secondsPerMove - steps * STEP_SECONDS, BOT_MIN_SECONDS, BOT_START_SECONDS),
  };
}

/** The static zebra rank nearest a bot rating (ties go to the lower rank). */
export function nearestRank(rating: number): BotLevel {
  return BOT_LEVELS.reduce((best, l) =>
    Math.abs(l.rating - rating) < Math.abs(best.rating - rating) ? l : best,
  );
}

/** 1-based rank number for the "Lv" meter. */
export function rankNumber(rating: number): number {
  return BOT_LEVELS.indexOf(nearestRank(rating)) + 1;
}

/** The ladder as the BotLevel useTugBot plays (rank id/colour for display). */
export function ladderBotLevel(ladder: BotLadder): BotLevel {
  const rank = nearestRank(ladder.rating);
  return { id: rank.id, color: rank.color, rating: ladder.rating, secondsPerMove: ladder.secondsPerMove };
}

/** Rating both sides' puzzles are drawn around: the bot, blended toward the player. */
export function targetRating(state: Pick<AdaptiveState, 'ladder' | 'player'>): number {
  const t = TARGET_BOT_WEIGHT * state.ladder.rating + (1 - TARGET_BOT_WEIGHT) * state.player.estimate;
  return Math.round(clamp(t, RATING_MIN, RATING_MAX));
}

export function initialAdaptive(saved: SavedAdaptive | null = null): AdaptiveState {
  const player = initialPlayer(saved);
  return { player, ladder: initialLadder(player.estimate), peakBeaten: null, trend: null };
}

export function adaptiveReducer(state: AdaptiveState, event: AdaptiveEvent): AdaptiveState {
  let { player, ladder, peakBeaten } = state;
  switch (event.type) {
    case 'HUMAN_SOLVED':
      player = updatePlayer(player, event.puzzleRating, true, event.seconds);
      peakBeaten = Math.max(peakBeaten ?? 0, ladder.rating);
      ladder = stepLadder(ladder, 1);
      break;
    case 'HUMAN_SKIPPED':
      player = updatePlayer(player, event.puzzleRating, false);
      break;
    case 'BOT_SOLVED':
      ladder = stepLadder(ladder, -DOWN_STEP);
      break;
    case 'CREEP':
      ladder = stepLadder(ladder, CREEP_STEP);
      break;
  }
  const before = rankNumber(state.ladder.rating);
  const after = rankNumber(ladder.rating);
  const trend = after > before ? 'up' : after < before ? 'down' : state.trend;
  return { player, ladder, peakBeaten, trend };
}

/** What a finished match persists, so the rematch starts near the player's level. */
export function toSaved(state: AdaptiveState, now: () => Date = () => new Date()): SavedAdaptive {
  return {
    estimate: Math.round(state.player.estimate),
    avgSeconds: state.player.avgSeconds === null ? null : Math.round(state.player.avgSeconds * 10) / 10,
    peakBotLevel: state.peakBeaten === null ? null : nearestRank(state.peakBeaten).id,
    date: now().toISOString(),
  };
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

const browserStorage = (): StorageLike | null => {
  try {
    return typeof window === 'undefined' ? null : window.localStorage;
  } catch {
    return null;
  }
};

export function saveAdaptive(saved: SavedAdaptive, storage: StorageLike | null = browserStorage()): void {
  try {
    storage?.setItem(STORAGE_KEY, JSON.stringify(saved));
  } catch {
    // Private mode / quota: the next match just starts fresh.
  }
}

/** The saved result, or null when absent or malformed. */
export function loadAdaptive(storage: StorageLike | null = browserStorage()): SavedAdaptive | null {
  try {
    const raw = JSON.parse(storage?.getItem(STORAGE_KEY) ?? 'null') as Partial<SavedAdaptive> | null;
    if (!raw || typeof raw.estimate !== 'number' || !Number.isFinite(raw.estimate)) return null;
    return {
      estimate: clamp(raw.estimate, RATING_MIN, RATING_MAX),
      avgSeconds: typeof raw.avgSeconds === 'number' ? raw.avgSeconds : null,
      peakBotLevel: BOT_LEVELS.some((l) => l.id === raw.peakBotLevel) ? (raw.peakBotLevel as BotLevelId) : null,
      date: typeof raw.date === 'string' ? raw.date : '',
    };
  } catch {
    return null;
  }
}
