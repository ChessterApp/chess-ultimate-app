import { describe, it, expect } from 'vitest';
import {
  isPromotionMove,
  promotionLayout,
  PROMOTION_ROLES,
} from '../promotion';

// White pawn on e7, white to move → e7e8 promotes (e8 kept empty).
const WHITE_PROMO = 'k7/4P3/8/8/8/8/8/7K w - - 0 1';
// Black pawn on d2, black to move → d2d1 promotes (d1 kept empty).
const BLACK_PROMO = 'K7/8/8/8/8/8/3p4/7k b - - 0 1';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
// White rook on a8 next to a black king — a rook reaching rank 8 is not a promotion.
const ROOK_ON_BACK = '3k4/8/8/8/8/8/8/R3K3 w - - 0 1';

describe('isPromotionMove', () => {
  it('detects a white pawn reaching the 8th rank', () => {
    expect(isPromotionMove(WHITE_PROMO, 'e7', 'e8')).toBe(true);
  });

  it('detects a black pawn reaching the 1st rank', () => {
    expect(isPromotionMove(BLACK_PROMO, 'd2', 'd1')).toBe(true);
  });

  it('is false for a pawn push that does not reach the last rank', () => {
    expect(isPromotionMove(START, 'e2', 'e4')).toBe(false);
  });

  it('is false when a non-pawn moves to the back rank', () => {
    expect(isPromotionMove(ROOK_ON_BACK, 'a1', 'a8')).toBe(false);
  });

  it('is false for an illegal move', () => {
    expect(isPromotionMove(WHITE_PROMO, 'e7', 'a1')).toBe(false);
  });

  it('is false for a malformed FEN', () => {
    expect(isPromotionMove('not a fen', 'e7', 'e8')).toBe(false);
  });
});

describe('promotionLayout', () => {
  it('offers queen, rook, bishop, knight in that order', () => {
    expect(promotionLayout('e8', 'white').map((c) => c.role)).toEqual(PROMOTION_ROLES);
    expect(PROMOTION_ROLES).toEqual(['q', 'r', 'b', 'n']);
  });

  it('drops the column downward from a top-edge square (white orientation, e8)', () => {
    const cells = promotionLayout('e8', 'white');
    // e-file is column 4 from the left when White is at the bottom.
    expect(cells.every((c) => c.col === 4)).toBe(true);
    expect(cells.map((c) => c.row)).toEqual([0, 1, 2, 3]);
  });

  it('grows the column upward when the promotion square sits on the bottom edge', () => {
    // Black promoting on d1, board shown from White's side → d1 is bottom row.
    const cells = promotionLayout('d1', 'white');
    expect(cells.every((c) => c.col === 3)).toBe(true);
    expect(cells.map((c) => c.row)).toEqual([7, 6, 5, 4]);
  });

  it('mirrors files and rows for a flipped (black) orientation', () => {
    // e8 with Black at the bottom: file mirrors to col 3, and rank 8 is the
    // bottom edge so the column grows upward.
    const cells = promotionLayout('e8', 'black');
    expect(cells.every((c) => c.col === 3)).toBe(true);
    expect(cells.map((c) => c.row)).toEqual([7, 6, 5, 4]);
  });
});
