import { describe, it, expect } from 'vitest';
import { orientationFromFen } from '../orientation';

describe('orientationFromFen', () => {
  it('puts black on the bottom when it is black to move', () => {
    expect(orientationFromFen('6k1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1')).toBe('black');
  });

  it('puts white on the bottom when it is white to move', () => {
    expect(orientationFromFen('6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1')).toBe('white');
  });

  it('re-derives per puzzle so a new FEN flips the board (regression: stale orientation on advance)', () => {
    const puzzle1 = '6k1/5ppp/8/8/8/8/5PPP/R5K1 b - - 0 1'; // black to move
    const puzzle2 = 'r5k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 1'; // white to move
    expect(orientationFromFen(puzzle1)).toBe('black');
    expect(orientationFromFen(puzzle2)).toBe('white');
    expect(orientationFromFen(puzzle1)).not.toBe(orientationFromFen(puzzle2));
  });

  it('defaults to white for a malformed FEN with no side-to-move field', () => {
    expect(orientationFromFen('6k1/5ppp/8/8/8/8/5PPP/R5K1')).toBe('white');
  });
});
