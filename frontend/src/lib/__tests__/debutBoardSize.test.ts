// Board + eval bar must fit phone widths without horizontal scroll.
import { describe, it, expect } from 'vitest';
import { debutBoardSize, evalBarGutter, EVAL_BAR_RESERVE_PX } from '../debutBoardSize';

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

describe('evalBarGutter', () => {
  const widths = [320, 340, 359, 360, 375, 390, 414, 600, 768, 1024, 1440];

  it.each(widths)('board + bar fit inside %ipx with the gutter kept', (width) => {
    const gutter = evalBarGutter(width);
    const board = debutBoardSize(width, gutter);
    // Bar sits left of the board: either in the gutter or in the side margin.
    const leftRoom = gutter + (width - gutter - board) / 2;
    expect(leftRoom).toBeGreaterThanOrEqual(EVAL_BAR_RESERVE_PX);
    expect(board + gutter).toBeLessThanOrEqual(width);
  });

  it('needs no gutter on normal phones and up', () => {
    for (const w of [360, 375, 390, 414, 768, 1440]) expect(evalBarGutter(w)).toBe(0);
  });

  it('keeps a gutter on very narrow phones', () => {
    expect(evalBarGutter(320)).toBe(EVAL_BAR_RESERVE_PX);
    expect(evalBarGutter(340)).toBe(EVAL_BAR_RESERVE_PX);
  });
});
