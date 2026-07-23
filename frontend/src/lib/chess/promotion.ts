import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';

/** Piece a pawn can promote to, in chess.js / UCI notation. */
export type PromotionRole = 'q' | 'r' | 'b' | 'n';

/** Order the picker column is drawn, from the promotion square inward. */
export const PROMOTION_ROLES: PromotionRole[] = ['q', 'r', 'b', 'n'];

/**
 * True when moving a pawn from `from` to `to` in the given position lands on
 * the last rank (i.e. requires a promotion choice). Confirms via chess.js that
 * the moving piece is a pawn and that the move is actually legal, so a stray
 * drag to the back rank by a non-pawn never triggers the picker.
 */
export function isPromotionMove(fen: string, from: Key, to: Key): boolean {
  try {
    const chess = new Chess(fen);
    const piece = chess.get(from as never);
    if (!piece || piece.type !== 'p') return false;

    const lastRank = piece.color === 'w' ? '8' : '1';
    if (to[1] !== lastRank) return false;

    return chess
      .moves({ square: from as never, verbose: true })
      .some((m) => m.to === to && !!m.promotion);
  } catch {
    return false;
  }
}

/** A single cell of the promotion picker, positioned by board grid coordinates. */
export interface PromotionCell {
  role: PromotionRole;
  /** Column index from the left of the displayed board (0–7). */
  col: number;
  /** Row index from the top of the displayed board (0–7). */
  row: number;
}

/**
 * Grid layout for the promotion picker column. The column sits on the file of
 * the target square and grows inward from whichever edge the promotion rank is
 * on, honouring board `orientation` so it reads correctly for both colours.
 */
export function promotionLayout(to: Key, orientation: 'white' | 'black'): PromotionCell[] {
  const fileIndex = to.charCodeAt(0) - 'a'.charCodeAt(0); // a=0 … h=7
  const rank = parseInt(to[1], 10); // 1–8

  const col = orientation === 'white' ? fileIndex : 7 - fileIndex;
  const edgeRow = orientation === 'white' ? 8 - rank : rank - 1; // 0 (top) or 7 (bottom)
  const growingDown = edgeRow === 0;

  return PROMOTION_ROLES.map((role, i) => ({
    role,
    col,
    row: growingDown ? i : 7 - i,
  }));
}
