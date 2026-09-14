import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { TUG_PUZZLES } from '../puzzles';

describe('TUG_PUZZLES data set', () => {
  it('has at least 40 puzzles with unique ids', () => {
    expect(TUG_PUZZLES.length).toBeGreaterThanOrEqual(40);
    const ids = new Set(TUG_PUZZLES.map((p) => p.id));
    expect(ids.size).toBe(TUG_PUZZLES.length);
  });

  it('every puzzle is legal and its solution line is valid', () => {
    for (const puzzle of TUG_PUZZLES) {
      const chess = new Chess();
      // FEN must load cleanly.
      expect(() => chess.load(puzzle.fen), `bad FEN in ${puzzle.id}`).not.toThrow();

      expect(puzzle.moves.length, `${puzzle.id} has no moves`).toBeGreaterThan(0);
      // The solving team plays first and last, so the line has odd length.
      expect(puzzle.moves.length % 2, `${puzzle.id} line parity`).toBe(1);

      puzzle.moves.forEach((uci, i) => {
        const legal = chess
          .moves({ verbose: true })
          .some((m) => `${m.from}${m.to}${m.promotion ?? ''}` === uci || `${m.from}${m.to}` === uci);
        expect(legal, `illegal move ${uci} (#${i}) in ${puzzle.id}`).toBe(true);
        chess.move({
          from: uci.slice(0, 2),
          to: uci.slice(2, 4),
          promotion: uci.length > 4 ? uci[4] : undefined,
        });
      });

      // rating sanity for an easy classroom set
      expect(puzzle.rating, `${puzzle.id} rating`).toBeGreaterThanOrEqual(400);
      expect(puzzle.rating, `${puzzle.id} rating`).toBeLessThanOrEqual(1400);
    }
  });

  it('mate puzzles end in checkmate', () => {
    for (const puzzle of TUG_PUZZLES) {
      const isMate = puzzle.themes.some((t) => t === 'mateIn1' || t === 'mateIn2');
      if (!isMate) continue;
      const chess = new Chess(puzzle.fen);
      for (const uci of puzzle.moves) {
        chess.move({
          from: uci.slice(0, 2),
          to: uci.slice(2, 4),
          promotion: uci.length > 4 ? uci[4] : undefined,
        });
      }
      expect(chess.isCheckmate(), `${puzzle.id} does not end in mate`).toBe(true);
    }
  });

  it('mateIn1 puzzles are exactly one move, mateIn2 exactly three', () => {
    for (const puzzle of TUG_PUZZLES) {
      if (puzzle.themes.includes('mateIn1')) {
        expect(puzzle.moves.length, `${puzzle.id}`).toBe(1);
      }
      if (puzzle.themes.includes('mateIn2')) {
        expect(puzzle.moves.length, `${puzzle.id}`).toBe(3);
      }
    }
  });
});
