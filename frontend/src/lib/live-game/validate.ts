/**
 * Server-side move validation via chess.js (BSD-2). The server always replays
 * from the stored `fen` and never trusts a client-supplied position.
 */

import { Chess } from 'chess.js';
import type { Turn } from './types';

export interface GameOver {
  /** '1-0' | '0-1' | '1/2-1/2' */
  result: string;
  /** checkmate | stalemate | insufficient_material | threefold | fifty_move */
  reason: string;
}

export interface ApplyMoveResult {
  ok: boolean;
  /** SAN of the applied move (only when ok). */
  san?: string;
  /** FEN after the move (only when ok). */
  fenAfter?: string;
  /** Set when the move ends the game; null otherwise. */
  gameOver: GameOver | null;
  /** Present when !ok. */
  error?: string;
}

/** Parse the active-colour field out of a FEN. */
export function turnFromFen(fen: string): Turn {
  return fen.split(' ')[1] === 'b' ? 'b' : 'w';
}

/**
 * Validate `uci` against `fen` and return the resulting SAN, FEN and any
 * game-over verdict. Illegal moves return `{ ok: false }` — never throw.
 *
 * UCI shape: `e2e4`, or `e7e8q` with a trailing promotion piece.
 */
export function applyMove(fen: string, uci: string): ApplyMoveResult {
  const move = uci.trim().toLowerCase();
  if (!/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(move)) {
    return { ok: false, gameOver: null, error: 'malformed_uci' };
  }

  const from = move.slice(0, 2);
  const to = move.slice(2, 4);
  const promotion = move.length === 5 ? move[4] : undefined;

  const chess = new Chess();
  try {
    chess.load(fen);
  } catch {
    return { ok: false, gameOver: null, error: 'bad_fen' };
  }

  try {
    // chess.js throws on an illegal move.
    const applied = chess.move({ from, to, promotion });
    if (!applied) {
      return { ok: false, gameOver: null, error: 'illegal_move' };
    }
  } catch {
    return { ok: false, gameOver: null, error: 'illegal_move' };
  }

  return {
    ok: true,
    san: chess.history().slice(-1)[0],
    fenAfter: chess.fen(),
    gameOver: detectGameOver(chess),
  };
}

/**
 * Classify the terminal state of `chess` after a move. The side to move in the
 * post-move position is the side that is checkmated / stalemated, so the winner
 * of a checkmate is the *other* side.
 */
function detectGameOver(chess: Chess): GameOver | null {
  if (!chess.isGameOver()) return null;

  if (chess.isCheckmate()) {
    // chess.turn() is the mated side → the mover won.
    const result = chess.turn() === 'w' ? '0-1' : '1-0';
    return { result, reason: 'checkmate' };
  }
  if (chess.isStalemate()) {
    return { result: '1/2-1/2', reason: 'stalemate' };
  }
  if (chess.isInsufficientMaterial()) {
    return { result: '1/2-1/2', reason: 'insufficient_material' };
  }
  if (chess.isThreefoldRepetition()) {
    return { result: '1/2-1/2', reason: 'threefold' };
  }
  if (chess.isDrawByFiftyMoves()) {
    return { result: '1/2-1/2', reason: 'fifty_move' };
  }
  // Any remaining draw condition.
  return { result: '1/2-1/2', reason: 'draw' };
}
