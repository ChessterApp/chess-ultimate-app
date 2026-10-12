import { describe, it, expect } from 'vitest';
import { MAX_RUN_PUZZLES, PACK_SIZE, TOPUP_THRESHOLD, newRunId, newSeed, retryDelay, topUpFrom } from '../pack';

describe('pack top-up', () => {
  it('tops up when fewer than 15 puzzles remain after the current one', () => {
    expect(PACK_SIZE).toBe(40);
    expect(TOPUP_THRESHOLD).toBe(15);
    expect(topUpFrom(40, 0)).toBeNull();
    expect(topUpFrom(40, 24)).toBeNull(); // 15 left
    expect(topUpFrom(40, 25)).toBe(40); // 14 left
    expect(topUpFrom(80, 65)).toBe(80);
  });

  it('never asks past the server cap', () => {
    expect(topUpFrom(MAX_RUN_PUZZLES, MAX_RUN_PUZZLES - 1)).toBeNull();
  });

  it('backs off silently: 1 s, 2 s, 4 s, then every 8 s', () => {
    expect([0, 1, 2, 3, 4, 9].map(retryDelay)).toEqual([1000, 2000, 4000, 8000, 8000, 8000]);
  });
});

describe('ids', () => {
  it('seeds are 16 hex chars (accepted by GET /pack)', () => {
    expect(newSeed()).toMatch(/^[0-9a-f]{16}$/);
    expect(newSeed()).not.toBe(newSeed());
  });

  it('run ids are UUID v4, with or without crypto.randomUUID', () => {
    const v4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    expect(newRunId()).toMatch(v4);
    const c = globalThis.crypto;
    Object.defineProperty(globalThis, 'crypto', { value: undefined, configurable: true });
    try {
      expect(newRunId()).toMatch(v4);
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: c, configurable: true });
    }
  });
});
