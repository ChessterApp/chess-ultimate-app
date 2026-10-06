import { describe, it, expect } from 'vitest';
import { sideToMoveCommand, withSideToMove } from '../CoachChat';

describe('side to move after a photo', () => {
  it.each([
    ['ход чёрных', 'b'], ['Ход черных.', 'b'], ['теперь ход чёрных', 'b'], ['чёрные ходят', 'b'],
    ['black to move', 'b'], ["Black's move", 'b'], ['қаралардың жүрісі', 'b'],
    ['ход белых', 'w'], ['white to move', 'w'], ['ақтардың жүрісі', 'w'],
  ])('%s → %s', (text, side) => {
    expect(sideToMoveCommand(text)).toBe(side);
  });

  it.each(['чей ход?', 'ход чёрных был плохой', 'Какой ход чёрных лучше?', 'black to move, what is best?'])(
    'a question is not a command: %s', (text) => {
      expect(sideToMoveCommand(text)).toBeNull();
    });

  it('switches the side and clears en passant', () => {
    const fen = 'r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 w - - 0 1';
    expect(withSideToMove(fen, 'b')).toBe('r2q1rk1/pp2bppp/4bn2/3P4/8/2N2N2/PP2BPPP/R2Q1RK1 b - - 0 1');
  });

  it('refuses a side that cannot be to move', () => {
    // White's king is in check from the rook on e8: Black cannot be to move.
    expect(withSideToMove('4r1k1/8/8/8/8/8/8/4K3 w - - 0 1', 'b')).toBeNull();
  });
});
