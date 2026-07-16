import { describe, it, expect } from 'vitest';
import { applyMove, turnFromFen } from '../validate';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('turnFromFen', () => {
  it('reads the active colour', () => {
    expect(turnFromFen(START)).toBe('w');
    expect(
      turnFromFen('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1'),
    ).toBe('b');
  });
});

describe('applyMove', () => {
  it('accepts a legal move and returns SAN + resulting FEN', () => {
    const r = applyMove(START, 'e2e4');
    expect(r.ok).toBe(true);
    expect(r.san).toBe('e4');
    expect(r.fenAfter?.split(' ')[1]).toBe('b');
    expect(r.gameOver).toBeNull();
  });

  it('rejects an illegal move without throwing', () => {
    const r = applyMove(START, 'e2e5');
    expect(r.ok).toBe(false);
    expect(r.fenAfter).toBeUndefined();
  });

  it('rejects a malformed uci', () => {
    const r = applyMove(START, 'zzzz');
    expect(r.ok).toBe(false);
    expect(r.error).toBe('malformed_uci');
  });

  it('detects checkmate (fool’s mate) and assigns the win to the mover', () => {
    // After 1.f3 e5 2.g4, black plays Qh4# — white is mated.
    const preMate =
      'rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2';
    const r = applyMove(preMate, 'd8h4');
    expect(r.ok).toBe(true);
    expect(r.gameOver).toEqual({ result: '0-1', reason: 'checkmate' });
  });

  it('detects stalemate as a draw', () => {
    // Black king h8, white king g1, white queen g5. Qg6 leaves black with no
    // legal move and not in check → stalemate.
    const preStalemate = '7k/8/8/6Q1/8/8/8/6K1 w - - 0 1';
    const r = applyMove(preStalemate, 'g5g6');
    expect(r.ok).toBe(true);
    expect(r.gameOver).toEqual({ result: '1/2-1/2', reason: 'stalemate' });
  });

  it('accepts a promotion uci (a7a8q)', () => {
    const r = applyMove('8/P3k3/8/8/8/8/8/4K3 w - - 0 1', 'a7a8q');
    expect(r.ok).toBe(true);
    expect(r.san).toBe('a8=Q');
  });

  it('accepts castling uci (e1g1)', () => {
    const r = applyMove(
      'r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1',
      'e1g1',
    );
    expect(r.ok).toBe(true);
    expect(r.san).toBe('O-O');
  });
});
