import { describe, it, expect } from 'vitest';
import { formatEngineLine, engineLineToString } from '../formatEngineLine';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('formatEngineLine', () => {
  it('numbers from the FEN fullmove number when White is to move', () => {
    const fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 12';
    const tokens = formatEngineLine(fen, ['e2e4', 'c7c5', 'g1f3', 'd7d6']);
    expect(tokens).toEqual([
      { num: '12.', san: 'e4' },
      { san: 'c5' },
      { num: '13.', san: 'Nf3' },
      { san: 'd6' },
    ]);
    expect(engineLineToString(tokens)).toBe('12.e4 c5 13.Nf3 d6');
  });

  it('uses an ellipsis for the first move when Black is to move', () => {
    // Najdorf after 5.Nc3 — Black to play move 5.
    const fen = 'rnbqkb1r/pp2pppp/3p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R b KQkq - 2 5';
    expect(engineLineToString(formatEngineLine(fen, ['a7a6', 'c1e3', 'e7e5']))).toBe('5…a6 6.Be3 e5');
  });

  it('caps at 4 full moves (8 half-moves) by default', () => {
    const pv = ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6', 'b5a4', 'g8f6', 'e1g1', 'f8e7', 'f1e1', 'b7b5', 'a4b3', 'd7d6', 'c2c3'];
    const tokens = formatEngineLine(START, pv);
    expect(tokens).toHaveLength(8);
    expect(engineLineToString(tokens)).toBe('1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6');
    expect(formatEngineLine(START, pv, 2)).toHaveLength(4);
  });

  it('handles promotions', () => {
    const fen = '8/4P3/8/8/8/k7/8/K7 w - - 0 60';
    expect(formatEngineLine(fen, ['e7e8q'])).toEqual([{ num: '60.', san: 'e8=Q' }]);
  });

  it('stops cleanly at an illegal or missing move', () => {
    expect(engineLineToString(formatEngineLine(START, ['e2e4', 'e7e5', 'e4e5', 'g1f3']))).toBe('1.e4 e5');
    expect(engineLineToString(formatEngineLine(START, ['e2e4', '', 'g1f3']))).toBe('1.e4');
  });

  it('returns [] for a bad FEN', () => {
    expect(formatEngineLine('not a fen', ['e2e4'])).toEqual([]);
    expect(formatEngineLine('', ['e2e4'])).toEqual([]);
  });
});
