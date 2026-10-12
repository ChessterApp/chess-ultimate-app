/**
 * Wire types for the Puzzle Rush backend (`backend/api/puzzle_rush.py`).
 * Instant-moves v2: the client plays the whole run from a prefetched puzzle
 * pack and records it once at the end (`POST /runs/finish`).
 *
 * Framework-free (shared with the mobile app): no React / DOM / Next imports.
 */

export type RushMode = '3min' | '5min' | 'survival';
export const RUSH_MODES: RushMode[] = ['3min', '5min', 'survival'];
export const MODE_SECONDS: Record<RushMode, number | null> = { '3min': 180, '5min': 300, survival: null };

export type RushPeriod = 'daily' | 'weekly' | 'all';
export type RushScope = 'global' | 'personal';
export type EndReason = 'strikes' | 'timeout' | 'quit';

type File = 'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'g' | 'h';
type Rank = '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8';
/** Board square, e.g. "e4" (assignable to chessground's `Key`). */
export type Square = `${File}${Rank}`;

/** One puzzle of a pack (`GET /pack`). */
export interface RushPuzzle {
  index: number;
  id: string;
  /** Position BEFORE the opponent's setup move. */
  fen: string;
  /** Full UCI line: moves[0] is the opponent setup, user moves at odd indices. */
  moves: string[];
  rating: number;
  themes: string[];
  /** The side the user plays. */
  color: 'white' | 'black';
}

export interface PackResponse {
  seed: string;
  from: number;
  count: number;
  puzzles: RushPuzzle[];
}

export type AttemptResult = 'solved' | 'failed' | 'unfinished';

export interface RunAttempt {
  index: number;
  puzzle_id: string;
  rating: number;
  result: AttemptResult;
  /** The user's own UCI moves, in order. */
  user_moves: string[];
  /** From the previous answer (or Go!) to this answer; null if unfinished. */
  ms: number | null;
}

export interface FinishRequest {
  run_id: string;
  mode: RushMode;
  seed: string;
  started_at: string;
  ended_at: string;
  end_reason: EndReason;
  attempts: RunAttempt[];
}

export interface RushResults {
  score: number;
  is_new_pb: boolean;
  longest_streak: number;
  highest_solved_rating: number | null;
  avg_ms_per_puzzle: number | null;
  duration_ms: number | null;
  personal_rank: number | null;
  global_rank: Record<RushPeriod, number> | null;
}

export interface FinishResponse extends RushResults {
  run_id: string;
  /** True when the run was already recorded (a retry); the stored result is returned. */
  duplicate: boolean;
}

export interface ModeBests {
  top_score: number | null;
  top_run_id: string | null;
  achieved_at: string | null;
  best_today: number | null;
}

export type BestsResponse = Record<RushMode, ModeBests>;

export interface LeaderboardEntry {
  rank: number;
  user_id?: string;
  display_name?: string | null;
  score: number;
  run_id: string;
  ended_at: string;
}

export interface LeaderboardResponse {
  mode: RushMode;
  period: RushPeriod;
  scope: RushScope;
  entries: LeaderboardEntry[];
  me?: { score: number; rank: number } | null;
}
