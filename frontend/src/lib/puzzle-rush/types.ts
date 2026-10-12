/**
 * Wire types for the Puzzle Rush backend (`backend/api/puzzle_rush.py`).
 * The server owns the clock and validates every move; the client never sees a
 * solution line while a run is active.
 */

export type RushMode = '3min' | '5min' | 'survival';
export const RUSH_MODES: RushMode[] = ['3min', '5min', 'survival'];
export const MODE_SECONDS: Record<RushMode, number | null> = { '3min': 180, '5min': 300, survival: null };

export type RushPeriod = 'daily' | 'weekly' | 'all';
export type RushScope = 'global' | 'personal';
export type EndReason = 'strikes' | 'timeout' | 'quit' | 'abandoned';

export interface RushPuzzle {
  id: string;
  index: number;
  /** Position BEFORE the opponent's setup move. */
  fen: string;
  setup_move: string;
  rating: number;
  /** The side the user plays. */
  color: 'white' | 'black';
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

export interface RunState {
  run_id: string;
  mode: RushMode;
  score: number;
  strikes: number;
  streak: number;
  started_at: string;
  deadline: string | null;
  server_now: string;
  run_over: boolean;
  end_reason?: EndReason;
}

export interface CreateRunResponse {
  run_id: string;
  mode: RushMode;
  started_at: string;
  deadline: string | null;
  server_now: string;
  puzzle: RushPuzzle;
  guest_token?: string;
}

export interface MoveResponse extends RunState {
  result: 'correct' | 'wrong' | 'solved';
  reply?: string;
  next_puzzle?: RushPuzzle;
  results?: RushResults;
}

export interface QuitResponse extends RunState {
  results: RushResults;
}

export interface RushAttempt {
  index: number;
  puzzle_id: string;
  rating: number;
  result: 'solved' | 'failed' | 'unfinished';
  user_moves: string[];
  ms: number | null;
  /** Present only once the run has ended. */
  fen?: string;
  solution?: string[];
}

export interface RunSummary extends RunState {
  longest_streak: number;
  highest_solved_rating: number | null;
  avg_ms_per_puzzle: number | null;
  duration_ms: number | null;
  ended_at: string | null;
  attempts: RushAttempt[];
  results?: RushResults;
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
