import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { buildPgnFromSanMoves, detectResult } from '@/lib/chess/boardEntry';

/**
 * Covers the manual move-entry ("Ввести ходы") logic wired into AddGameModal:
 * turning board interaction (via chess.js SAN) into a PGN with the source
 * `board_entry` and auto-detecting the result on terminal positions.
 */

// Replays from/to moves on a fresh board the way BoardEntryTab.handleMove does,
// collecting the resulting SAN list.
function playMoves(moves: Array<{ from: string; to: string; promotion?: string }>): {
  san: string[];
  chess: Chess;
} {
  const chess = new Chess();
  const san: string[] = [];
  for (const m of moves) {
    const move = chess.move({ from: m.from, to: m.to, promotion: (m.promotion ?? 'q') as never });
    san.push(move.san);
  }
  return { san, chess };
}

describe('buildPgnFromSanMoves', () => {
  it('returns an empty string when there are no moves', () => {
    expect(buildPgnFromSanMoves([])).toBe('');
  });

  it('builds numbered movetext with a trailing * for an unfinished game', () => {
    const { san } = playMoves([
      { from: 'e2', to: 'e4' },
      { from: 'e7', to: 'e5' },
      { from: 'g1', to: 'f3' },
    ]);
    const pgn = buildPgnFromSanMoves(san, '*');
    expect(pgn).toBe('1. e4 e5 2. Nf3 *');
    // Contains the entered SAN moves.
    for (const s of san) expect(pgn).toContain(s);
  });

  it('uses the supplied result token as the trailing marker', () => {
    const { san } = playMoves([
      { from: 'e2', to: 'e4' },
      { from: 'e7', to: 'e5' },
    ]);
    expect(buildPgnFromSanMoves(san, '1-0')).toBe('1. e4 e5 1-0');
  });

  it('produces a PGN that chess.js can load back', () => {
    const { san } = playMoves([
      { from: 'e2', to: 'e4' },
      { from: 'e7', to: 'e5' },
      { from: 'g1', to: 'f3' },
      { from: 'b8', to: 'c6' },
    ]);
    const pgn = buildPgnFromSanMoves(san, '*');
    const reloaded = new Chess();
    reloaded.loadPgn(pgn);
    expect(reloaded.history()).toEqual(san);
  });
});

describe('detectResult', () => {
  it('returns null for a non-terminal position', () => {
    const { chess } = playMoves([{ from: 'e2', to: 'e4' }]);
    expect(detectResult(chess)).toBeNull();
  });

  it("returns 1-0 when Black is checkmated (Scholar's mate)", () => {
    const { chess } = playMoves([
      { from: 'e2', to: 'e4' },
      { from: 'e7', to: 'e5' },
      { from: 'f1', to: 'c4' },
      { from: 'b8', to: 'c6' },
      { from: 'd1', to: 'h5' },
      { from: 'g8', to: 'f6' },
      { from: 'h5', to: 'f7' }, // Qxf7#
    ]);
    expect(chess.isCheckmate()).toBe(true);
    expect(detectResult(chess)).toBe('1-0');
  });

  it("returns 0-1 when White is checkmated (Fool's mate)", () => {
    const { chess } = playMoves([
      { from: 'f2', to: 'f3' },
      { from: 'e7', to: 'e5' },
      { from: 'g2', to: 'g4' },
      { from: 'd8', to: 'h4' }, // Qh4#
    ]);
    expect(chess.isCheckmate()).toBe(true);
    expect(detectResult(chess)).toBe('0-1');
  });

  it('returns 1/2-1/2 for a stalemate', () => {
    // Classic stalemate position, Black to move with no legal moves.
    const chess = new Chess('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1');
    expect(chess.isStalemate()).toBe(true);
    expect(detectResult(chess)).toBe('1/2-1/2');
  });

  it('returns 1/2-1/2 for insufficient material (lone kings)', () => {
    const chess = new Chess('7k/8/6K1/8/8/8/8/8 w - - 0 1');
    expect(chess.isInsufficientMaterial()).toBe(true);
    expect(detectResult(chess)).toBe('1/2-1/2');
  });
});
