import { describe, it, expect } from 'vitest';
import { pickIndex } from '../random';

describe('pickIndex', () => {
  it('always returns 0 for a single segment', () => {
    expect(pickIndex(1)).toBe(0);
  });

  it('rejects invalid counts', () => {
    expect(() => pickIndex(0)).toThrow();
    expect(() => pickIndex(-3)).toThrow();
    expect(() => pickIndex(2.5)).toThrow();
  });

  it('always returns an index within [0, count)', () => {
    for (let i = 0; i < 2000; i++) {
      const idx = pickIndex(7);
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThan(7);
      expect(Number.isInteger(idx)).toBe(true);
    }
  });

  it('is approximately uniform across segments', () => {
    const count = 6;
    const trials = 60000;
    const buckets = new Array(count).fill(0);
    for (let i = 0; i < trials; i++) buckets[pickIndex(count)] += 1;
    const expected = trials / count;
    for (const c of buckets) {
      // Within 15% of the expected frequency — generous, but catches gross bias.
      expect(Math.abs(c - expected) / expected).toBeLessThan(0.15);
    }
  });

  it('rejects values that would introduce modulo bias', () => {
    // count = 7 does not divide 2^32; values in the top reject band must be
    // discarded and re-drawn. (Values are kept within uint32 to avoid wrap.)
    const limit = 0x100000000 - (0x100000000 % 7); // largest usable value + 1
    const queued = [limit, limit + 1, 10]; // first two rejected, third used
    let call = 0;
    const rng = () => queued[call++];
    expect(pickIndex(7, rng)).toBe(10 % 7);
    expect(call).toBe(3);
  });

  it('uses the injected rng for a clean value', () => {
    expect(pickIndex(4, () => 9)).toBe(1);
  });
});
