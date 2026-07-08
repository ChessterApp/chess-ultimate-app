import { describe, it, expect } from 'vitest';
import {
  evaluateLineMove,
  movesMatch,
  promotionPiece,
  colorToMove,
} from '../solutionLine';

describe('promotionPiece', () => {
  it('returns the promotion letter for a promotion move', () => {
    expect(promotionPiece('e7e8q')).toBe('q');
    expect(promotionPiece('a2a1N')).toBe('n');
  });
  it('returns undefined for a normal move', () => {
    expect(promotionPiece('e2e4')).toBeUndefined();
  });
});

describe('movesMatch', () => {
  it('matches on from/to squares', () => {
    expect(movesMatch('f1', 'f6', 'f1f6')).toBe(true);
  });
  it('matches a promotion by from/to only', () => {
    expect(movesMatch('e7', 'e8', 'e7e8q')).toBe(true);
  });
  it('rejects a different move', () => {
    expect(movesMatch('f1', 'f5', 'f1f6')).toBe(false);
  });
  it('rejects when expected is empty', () => {
    expect(movesMatch('f1', 'f6', '')).toBe(false);
  });
});

describe('colorToMove', () => {
  it('reads the side to move from a FEN', () => {
    expect(colorToMove('6K1/8/6kq/8/8/8/8/5R2 w - - 0 1')).toBe('white');
    expect(colorToMove('6K1/8/6kq/8/8/8/8/5R2 b - - 0 1')).toBe('black');
  });
});

describe('evaluateLineMove', () => {
  const line = ['f1f6', 'g6h5', 'f6h6']; // mate in two: user, opponent, user

  it('reports progress and the opponent reply on the first correct move', () => {
    const r = evaluateLineMove(line, 0, 'f1', 'f6');
    expect(r.kind).toBe('progress');
    if (r.kind === 'progress') {
      expect(r.userMove).toBe('f1f6');
      expect(r.opponentMove).toBe('g6h5');
      expect(r.nextIndex).toBe(2); // user's next move index
    }
  });

  it('reports solved on the final correct move', () => {
    const r = evaluateLineMove(line, 2, 'f6', 'h6');
    expect(r.kind).toBe('solved');
    if (r.kind === 'solved') {
      expect(r.userMove).toBe('f6h6');
      expect(r.nextIndex).toBe(3);
    }
  });

  it('reports incorrect for a wrong move mid-line (index preserved by caller)', () => {
    const r = evaluateLineMove(line, 0, 'f1', 'f2');
    expect(r.kind).toBe('incorrect');
  });

  it('reports incorrect for a wrong move at a later step', () => {
    const r = evaluateLineMove(line, 2, 'f6', 'f7');
    expect(r.kind).toBe('incorrect');
  });

  it('single-move line solves immediately (fallback case)', () => {
    const r = evaluateLineMove(['e2e4'], 0, 'e2', 'e4');
    expect(r.kind).toBe('solved');
    if (r.kind === 'solved') {
      expect(r.nextIndex).toBe(1);
    }
  });

  it('carries the promotion piece for a promoting user move', () => {
    const r = evaluateLineMove(['e7e8q'], 0, 'e7', 'e8');
    expect(r.kind).toBe('solved');
    if (r.kind === 'solved') {
      expect(r.userPromotion).toBe('q');
    }
  });

  it('carries the opponent promotion when the reply promotes', () => {
    const r = evaluateLineMove(['a1a2', 'b2b1q', 'a2a1'], 0, 'a1', 'a2');
    expect(r.kind).toBe('progress');
    if (r.kind === 'progress') {
      expect(r.opponentPromotion).toBe('q');
    }
  });
});
