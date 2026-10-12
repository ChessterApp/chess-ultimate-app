/**
 * Local move validation for Puzzle Rush (same rule the v1 backend applied in
 * `submit_move`): a move is correct when it is the expected move of the line OR
 * any checkmating move (§7.4); it solves the puzzle when it mates or was the
 * line's last move. Promotions are compared as moves, not strings, so an
 * omitted promotion piece defaults to a queen.
 *
 * Framework-free (shared with the mobile app): chess.js only.
 */

import { Chess } from 'chess.js';
import type { Square } from './types';

export interface AppliedMove {
  fen: string;
  from: Square;
  to: Square;
  /** Normalised UCI actually played (promotion piece included). */
  uci: string;
  capture: boolean;
}

/** Apply a UCI move to a FEN; null if the move is not legal there. */
export function applyUci(fen: string, uci: string): AppliedMove | null {
  try {
    const chess = new Chess(fen);
    const from = uci.slice(0, 2) as Square;
    const to = uci.slice(2, 4) as Square;
    let promotion = uci[4];
    if (!promotion) {
      const piece = chess.get(from);
      if (piece?.type === 'p' && (to[1] === '8' || to[1] === '1')) promotion = 'q';
    }
    const m = chess.move({ from, to, promotion });
    return { fen: chess.fen(), from, to, uci: `${m.from}${m.to}${m.promotion ?? ''}`, capture: Boolean(m.captured) };
  } catch {
    return null;
  }
}

export type MoveVerdict =
  | { kind: 'illegal' }
  | (AppliedMove & {
      kind: 'wrong' | 'correct' | 'solved';
      /** Opponent reply to play next (only for a correct, non-final move). */
      reply: string | null;
    });

/**
 * Judge the user's `uci` in `fen`, where `moves[ply]` is the expected move
 * (`fen` is the position after `moves[0..ply-1]`).
 */
export function judgeMove(fen: string, moves: string[], ply: number, uci: string): MoveVerdict {
  const played = applyUci(fen, uci);
  if (!played) return { kind: 'illegal' };
  const mate = new Chess(played.fen).isCheckmate();
  const expected = moves[ply] ? applyUci(fen, moves[ply]) : null;
  const correct = mate || (expected !== null && expected.fen === played.fen);
  if (!correct) return { ...played, kind: 'wrong', reply: null };
  const solved = mate || ply >= moves.length - 1;
  return { ...played, kind: solved ? 'solved' : 'correct', reply: solved ? null : moves[ply + 1] ?? null };
}
