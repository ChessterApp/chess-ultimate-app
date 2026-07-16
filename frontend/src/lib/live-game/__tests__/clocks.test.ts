import { describe, it, expect } from 'vitest';
import { computeClocksAfterMove, remainingMs } from '../clocks';

const T0 = 1_000_000; // arbitrary epoch-ms baseline

describe('computeClocksAfterMove', () => {
  it('deducts the mover elapsed time from their bank', () => {
    const r = computeClocksAfterMove({
      whiteMs: 60_000,
      blackMs: 60_000,
      lastMoveAt: T0,
      now: T0 + 5_000,
      turn: 'w',
      incrementSec: 0,
    });
    expect(r.flagged).toBe(false);
    expect(r.whiteMs).toBe(55_000);
    expect(r.blackMs).toBe(60_000); // idle side untouched
  });

  it('applies increment after deducting elapsed', () => {
    const r = computeClocksAfterMove({
      whiteMs: 60_000,
      blackMs: 60_000,
      lastMoveAt: T0,
      now: T0 + 3_000,
      turn: 'b',
      incrementSec: 5,
    });
    expect(r.flagged).toBe(false);
    // black: 60000 - 3000 + 5000
    expect(r.blackMs).toBe(62_000);
    expect(r.whiteMs).toBe(60_000);
  });

  it('flags at the exact zero boundary (bank - elapsed === 0)', () => {
    const r = computeClocksAfterMove({
      whiteMs: 5_000,
      blackMs: 60_000,
      lastMoveAt: T0,
      now: T0 + 5_000, // elapsed exactly equals bank
      turn: 'w',
      incrementSec: 5, // increment NOT applied on flag
    });
    expect(r.flagged).toBe(true);
    expect(r.whiteMs).toBe(0);
    expect(r.blackMs).toBe(60_000);
  });

  it('flags when the mover overruns their bank', () => {
    const r = computeClocksAfterMove({
      whiteMs: 4_000,
      blackMs: 60_000,
      lastMoveAt: T0,
      now: T0 + 9_000,
      turn: 'w',
      incrementSec: 2,
    });
    expect(r.flagged).toBe(true);
    expect(r.whiteMs).toBe(0);
  });

  it('short-circuits untimed games (null banks): no deduction, never flagged', () => {
    const r = computeClocksAfterMove({
      whiteMs: null,
      blackMs: null,
      lastMoveAt: T0,
      now: T0 + 999_999,
      turn: 'w',
      incrementSec: null,
    });
    expect(r).toEqual({ whiteMs: null, blackMs: null, flagged: false });
  });

  it('treats a null lastMoveAt as zero elapsed', () => {
    const r = computeClocksAfterMove({
      whiteMs: 30_000,
      blackMs: 30_000,
      lastMoveAt: null,
      now: T0,
      turn: 'b',
      incrementSec: 0,
    });
    expect(r.blackMs).toBe(30_000);
    expect(r.flagged).toBe(false);
  });
});

describe('remainingMs', () => {
  it('debits only the side to move (white)', () => {
    const c = remainingMs(
      {
        whiteMs: 40_000,
        blackMs: 50_000,
        lastMoveAt: T0,
        turn: 'w',
        status: 'active',
      },
      T0 + 7_000,
    );
    expect(c).toEqual({ whiteMs: 33_000, blackMs: 50_000 });
  });

  it('debits only the side to move (black)', () => {
    const c = remainingMs(
      {
        whiteMs: 40_000,
        blackMs: 50_000,
        lastMoveAt: T0,
        turn: 'b',
        status: 'active',
      },
      T0 + 12_000,
    );
    expect(c).toEqual({ whiteMs: 40_000, blackMs: 38_000 });
  });

  it('never goes negative (floors at 0)', () => {
    const c = remainingMs(
      {
        whiteMs: 3_000,
        blackMs: 50_000,
        lastMoveAt: T0,
        turn: 'w',
        status: 'active',
      },
      T0 + 10_000,
    );
    expect(c.whiteMs).toBe(0);
  });

  it('returns stored banks verbatim for untimed games', () => {
    const c = remainingMs(
      {
        whiteMs: null,
        blackMs: null,
        lastMoveAt: T0,
        turn: 'w',
        status: 'active',
      },
      T0 + 5_000,
    );
    expect(c).toEqual({ whiteMs: null, blackMs: null });
  });

  it('does not tick for non-active games', () => {
    const c = remainingMs(
      {
        whiteMs: 40_000,
        blackMs: 50_000,
        lastMoveAt: T0,
        turn: 'w',
        status: 'finished',
      },
      T0 + 30_000,
    );
    expect(c).toEqual({ whiteMs: 40_000, blackMs: 50_000 });
  });
});
