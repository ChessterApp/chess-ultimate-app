/**
 * Coach types for the AI Chess Coach feature (board protocol + sessions)
 */

import { Key } from 'chessground/types';

// ─── Board Actions (matches Hermes board_protocol.py) ────────────────────

export interface SetFenAction {
  type: 'set_fen';
  fen: string;
}

export interface LoadPgnAction {
  type: 'load_pgn';
  pgn: string;
}

export interface SetPuzzleAction {
  type: 'set_puzzle';
  fen: string;
  solution: string[];
  /** Lichess puzzle id when the puzzle came from the puzzle database. */
  puzzle_id?: string;
}

export interface DrawArrowsAction {
  type: 'draw_arrows';
  arrows: Array<{ from: string; to: string; brush: string }>;
}

export interface HighlightSquaresAction {
  type: 'highlight_squares';
  squares: string[];
  color: string;
}

export interface NavigateAction {
  type: 'navigate';
  direction: 'first' | 'prev' | 'next' | 'last';
}

export interface FlipBoardAction {
  type: 'flip_board';
}

export interface ClearBoardAction {
  type: 'clear_board';
}

/** Every action may name the board (tab) it targets; absent = the active board. */
type Addressed = { board_id?: string };

export type BoardAction = Addressed &
  (
  | SetFenAction
  | LoadPgnAction
  | SetPuzzleAction
  | DrawArrowsAction
  | HighlightSquaresAction
  | NavigateAction
  | FlipBoardAction
  | ClearBoardAction
  );

// ─── Game Results (from TWIC search) ─────────────────────────────────────

export interface GameResult {
  /** TWIC row id (number) or a saved-game uuid / import index (string). */
  id: number | string;
  white_name: string;
  black_name: string;
  result: string;
  date: string;
  eco: string;
  opening: string;
  event: string;
  white_elo: number | null;
  black_elo: number | null;
  /**
   * Where the game comes from. Absent or 'twic' → the PGN is fetched from the
   * master database; 'user' / 'lichess' / 'chesscom' → the card carries `pgn`.
   */
  source?: 'twic' | 'user' | 'lichess' | 'chesscom' | string;
  pgn?: string;
}

// ─── Coach Response ──────────────────────────────────────────────────────

export interface CoachResponse {
  message: string;
  board_actions: BoardAction[];
}

// ─── Coach Session ───────────────────────────────────────────────────────

export interface CoachSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
}

// ─── Coach Message ───────────────────────────────────────────────────────

export interface CoachMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  fen?: string;
  timestamp: Date;
  boardActions?: BoardAction[];
  gameResults?: GameResult[];
  /**
   * Turn correlation id for a COMPLETED assistant answer — arrives on the final
   * SSE frame. Used to attach 👍/👎 feedback; absent while streaming.
   */
  turnId?: string;
}

// ─── Puzzle State ────────────────────────────────────────────────────────

export interface PuzzleState {
  fen: string;
  solution: string[];
  currentMoveIndex: number;
  solved: boolean;
}

// ─── Coach Board State ───────────────────────────────────────────────────

export interface CoachBoardState {
  fen: string;
  pgn: string;
  moveIndex: number;
  arrows: Array<{ from: Key; to: Key; brush: string }>;
  highlights: Key[];
  orientation: 'white' | 'black';
  puzzleMode: boolean;
  puzzleState: PuzzleState | null;
}
