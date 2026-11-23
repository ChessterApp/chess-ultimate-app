import { describe, it, expect } from 'vitest';
import { computeLegalDests, getChessgroundConfig } from '../chessgroundConfig';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('computeLegalDests', () => {
  it('maps each movable square to its legal destinations', () => {
    const dests = computeLegalDests(START)!;
    expect(dests.get('e2')).toEqual(['e3', 'e4']);
    expect(dests.get('g1')?.sort()).toEqual(['f3', 'h3']);
    expect(dests.has('e1')).toBe(false);
    expect([...dests.values()].flat()).toHaveLength(20);
  });

  it('returns undefined for lesson FENs chess.js rejects', () => {
    expect(computeLegalDests('8/8/8/8/8/8/8/R7 w - - 0 1')).toBeUndefined();
    expect(computeLegalDests('not a fen')).toBeUndefined();
  });
});

describe('getChessgroundConfig showLegalDests', () => {
  const onMove = () => {};

  it('keeps dots off by default', () => {
    const cfg = getChessgroundConfig({ fen: START, onMove });
    expect(cfg.movable?.showDests).toBe(false);
    expect(cfg.movable?.dests).toBeUndefined();
  });

  it('shows dots with free moves still allowed', () => {
    const cfg = getChessgroundConfig({ fen: START, onMove, showLegalDests: true });
    expect(cfg.movable?.showDests).toBe(true);
    expect(cfg.movable?.free).toBe(true);
    expect(cfg.movable?.dests?.get('e2')).toEqual(['e3', 'e4']);
    expect(cfg.selectable?.enabled).toBe(true);
  });

  it('falls back to free moves without dots for a non-standard FEN', () => {
    const cfg = getChessgroundConfig({ fen: '8/8/8/8/8/8/8/R7 w - - 0 1', onMove, showLegalDests: true });
    expect(cfg.movable?.dests).toBeUndefined();
    expect(cfg.movable?.free).toBe(true);
  });
});
