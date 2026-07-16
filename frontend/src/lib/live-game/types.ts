/**
 * Shared types for online play (challenge-link live games).
 *
 * These mirror the `games` / `game_moves` schema from
 * supabase/migrations/20260716_026_online_play.sql. DB columns are snake_case;
 * the app-facing shapes below are camelCase (converted at the route boundary).
 */

export type GameStatus =
  | 'challenge'
  | 'active'
  | 'finished'
  | 'aborted'
  | 'expired';

export type ColorChoice = 'white' | 'black' | 'random';

/** 'w' | 'b' as encoded in a FEN's active-colour field. */
export type Turn = 'w' | 'b';

/** A `games` row as returned by supabase-js (snake_case, nullable where the DB is). */
export interface GameRow {
  id: string;
  creator_id: string;
  opponent_id: string | null;
  white_id: string | null;
  black_id: string | null;
  status: GameStatus;
  color_choice: ColorChoice;
  initial_sec: number | null;
  increment_sec: number | null;
  fen: string;
  ply: number;
  white_ms: number | null;
  black_ms: number | null;
  last_move_at: string | null;
  result: string | null;
  winner_id: string | null;
  end_reason: string | null;
  draw_offer_by: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

/** A `game_moves` row. */
export interface GameMoveRow {
  game_id: string;
  ply: number;
  uci: string;
  san: string | null;
  fen_after: string | null;
  move_time_ms: number | null;
  created_at: string;
}

/** Live clock banks, in milliseconds. `null` on both = untimed game. */
export interface Clocks {
  whiteMs: number | null;
  blackMs: number | null;
}

/** Hydration payload returned by `GET /api/games/[gameId]`. */
export interface HydrationPayload {
  game: {
    id: string;
    status: GameStatus;
    colorChoice: ColorChoice;
    initialSec: number | null;
    incrementSec: number | null;
    fen: string;
    ply: number;
    whiteMs: number | null;
    blackMs: number | null;
    result: string | null;
    winnerId: string | null;
    endReason: string | null;
    /** Clerk id of the player with a standing draw offer, or null. */
    drawOfferBy?: string | null;
    creatorId: string;
    // Player identities are only exposed once the game leaves 'challenge'.
    whiteId?: string | null;
    blackId?: string | null;
    opponentId?: string | null;
  };
  moves: Array<{
    ply: number;
    uci: string;
    san: string | null;
    fenAfter: string | null;
    moveTimeMs: number | null;
  }>;
}

/** Realtime broadcast event names on topic `game:{id}`. */
export type BroadcastEvent =
  | 'game.start'
  | 'game.move'
  | 'game.end'
  | 'game.draw_offer'
  | 'game.draw_decline';

export interface GameStartPayload {
  gameId: string;
  status: GameStatus;
  fen: string;
  whiteId: string | null;
  blackId: string | null;
  whiteMs: number | null;
  blackMs: number | null;
  lastMoveAt: string | null;
}

export interface GameMovePayload {
  ply: number;
  uci: string;
  san: string;
  fenAfter: string;
  whiteMs: number | null;
  blackMs: number | null;
  gameOver?: { result: string; reason: string };
}

export interface GameEndPayload {
  gameId: string;
  /** '1-0' | '0-1' | '1/2-1/2', or null for a non-result end (abort). */
  result: string | null;
  winnerId: string | null;
  reason: string;
  /** Terminal status — 'finished' for resign/draw/flag/mate, 'aborted' for abort.
   * Defaults to 'finished' in the reducer when omitted. */
  status?: GameStatus;
  whiteMs: number | null;
  blackMs: number | null;
}

export interface GameDrawOfferPayload {
  gameId: string;
  /** Clerk id of the player making the offer. */
  by: string;
}

export interface GameDrawDeclinePayload {
  gameId: string;
}
