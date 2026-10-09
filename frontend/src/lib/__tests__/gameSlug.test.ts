import { describe, it, expect } from 'vitest';
import { encodeGameSlug, decodeGameSlug } from '@/lib/gameSlug';

describe('gameSlug codec', () => {
  const ids = [0, 1, 42, 999999, 2147483647, 9007199254740991];

  it('round-trips twic games', () => {
    for (const id of ids) {
      const slug = encodeGameSlug('twic', id);
      expect(decodeGameSlug(slug)).toEqual({ source: 'twic', id });
    }
  });

  it('round-trips lichess games', () => {
    for (const id of ids) {
      const slug = encodeGameSlug('lichess', id);
      expect(decodeGameSlug(slug)).toEqual({ source: 'lichess', id });
    }
  });

  it('emits alphanumeric slugs of at least the min length', () => {
    const slug = encodeGameSlug('twic', 12345);
    expect(slug).toMatch(/^[A-Za-z0-9]+$/);
    expect(slug.length).toBeGreaterThanOrEqual(7);
  });

  it('never exposes a data-source name in the slug', () => {
    for (const source of ['twic', 'lichess'] as const) {
      for (const id of ids) {
        const slug = encodeGameSlug(source, id).toLowerCase();
        expect(slug).not.toContain('twic');
        expect(slug).not.toContain('lichess');
      }
    }
  });

  it('distinguishes sources for the same id', () => {
    expect(encodeGameSlug('twic', 500)).not.toEqual(encodeGameSlug('lichess', 500));
  });

  it('returns null for garbage / invalid slugs', () => {
    expect(decodeGameSlug('')).toBeNull();
    expect(decodeGameSlug('!!!')).toBeNull();
    expect(decodeGameSlug('not a slug')).toBeNull();
    // @ts-expect-error — intentionally wrong type
    expect(decodeGameSlug(null)).toBeNull();
    // @ts-expect-error — intentionally wrong type
    expect(decodeGameSlug(undefined)).toBeNull();
  });

  it('rejects non-canonical encodings via the round-trip guard', () => {
    // A single character cannot be a valid 2-number minLength-7 encoding.
    expect(decodeGameSlug('a')).toBeNull();
    // Mutating a valid slug should (almost always) fail the round-trip check.
    const valid = encodeGameSlug('twic', 777);
    const mutated = valid.slice(0, -1) + (valid.endsWith('a') ? 'b' : 'a');
    const decoded = decodeGameSlug(mutated);
    if (decoded) {
      // If it happens to decode, it must still be a strict canonical round-trip.
      expect(encodeGameSlug(decoded.source, decoded.id)).toBe(mutated);
    }
  });

  it('throws on invalid encode input', () => {
    // @ts-expect-error — bad source
    expect(() => encodeGameSlug('chesscom', 1)).toThrow();
    expect(() => encodeGameSlug('twic', -1)).toThrow();
    expect(() => encodeGameSlug('twic', 1.5)).toThrow();
  });
});
