import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { TUG_PUZZLES } from '../puzzles';
import { TUG_LEVELS, TUG_THEMES } from '../prefetch';

describe('TUG_PUZZLES data set', () => {
  it('has ~300 puzzles with unique ids', () => {
    expect(TUG_PUZZLES.length).toBeGreaterThanOrEqual(280);
    const ids = new Set(TUG_PUZZLES.map((p) => p.id));
    expect(ids.size).toBe(TUG_PUZZLES.length);
  });

  it('covers every level band with every setup-screen theme', () => {
    for (const band of TUG_LEVELS) {
      const inBand = TUG_PUZZLES.filter((p) => p.rating >= band.ratingFrom && p.rating <= band.ratingTo);
      expect(inBand.length, band.id).toBeGreaterThanOrEqual(70);
      for (const { tag } of TUG_THEMES) {
        expect(inBand.some((p) => p.themes.includes(tag)), `${band.id}/${tag}`).toBe(true);
      }
    }
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

      // inside the Pawn..Queen bands
      expect(puzzle.rating, `${puzzle.id} rating`).toBeGreaterThanOrEqual(400);
      expect(puzzle.rating, `${puzzle.id} rating`).toBeLessThanOrEqual(2400);
    }
    // Replays ~300 lines with chess.js; slower than 5s when the whole suite runs in parallel.
  }, 30_000);

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

  it('no mateIn2 puzzle has a mate-in-1 shortcut (would be a mislabeled win)', () => {
    const mateIn2 = TUG_PUZZLES.filter((p) => p.themes.includes('mateIn2'));
    expect(mateIn2.length, 'expected some mateIn2 puzzles').toBeGreaterThan(0);
    for (const puzzle of mateIn2) {
      const chess = new Chess(puzzle.fen);
      const hasShorterMate = chess.moves({ verbose: true }).some((m) => {
        const probe = new Chess(puzzle.fen);
        probe.move({ from: m.from, to: m.to, promotion: m.promotion ?? 'q' });
        return probe.isCheckmate();
      });
      expect(hasShorterMate, `${puzzle.id} is solvable in one move`).toBe(false);
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
