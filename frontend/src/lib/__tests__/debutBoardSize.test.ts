// Board + eval bar must fit phone widths without horizontal scroll.
import { describe, it, expect } from 'vitest';
import { debutBoardSize, EVAL_BAR_RESERVE_PX } from '../debutBoardSize';

describe('debutBoardSize', () => {
  it('keeps the existing sizes with no eval bar', () => {
    expect(debutBoardSize(360)).toBe(320);
    expect(debutBoardSize(390)).toBe(320);
    expect(debutBoardSize(1280)).toBe(520);
  });

  it.each([320, 360, 375, 390, 414])('board + eval bar fit inside %ipx', (width) => {
    const board = debutBoardSize(width, EVAL_BAR_RESERVE_PX);
    expect(board + EVAL_BAR_RESERVE_PX).toBeLessThanOrEqual(width - 24);
    expect(board).toBeGreaterThan(250);
  });

  it('does not shrink a desktop board for the eval bar', () => {
    expect(debutBoardSize(1280, EVAL_BAR_RESERVE_PX)).toBe(520);
  });
});
