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
  move_index: number;
}

export interface FlipBoardAction {
  type: 'flip_board';
}

export interface ClearBoardAction {
  type: 'clear_board';
}

export type BoardAction =
  | SetFenAction
  | LoadPgnAction
  | SetPuzzleAction
  | DrawArrowsAction
  | HighlightSquaresAction
  | NavigateAction
  | FlipBoardAction
  | ClearBoardAction;

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
