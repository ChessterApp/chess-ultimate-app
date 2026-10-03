import { describe, expect, it } from 'vitest';
import { companionIdempotencyKey, isCompanionEnabled } from '../companion-rules';

describe('isCompanionEnabled', () => {
  it('defaults to false for nullish / non-object input', () => {
    expect(isCompanionEnabled(null)).toBe(false);
    expect(isCompanionEnabled(undefined)).toBe(false);
    expect(isCompanionEnabled(42)).toBe(false);
    expect(isCompanionEnabled('true')).toBe(false);
  });

  it('is false when the flag is missing or falsy', () => {
    expect(isCompanionEnabled({})).toBe(false);
    expect(isCompanionEnabled({ companions_enabled: false })).toBe(false);
    expect(isCompanionEnabled({ companions_enabled: 'true' })).toBe(false); // must be strict true
    expect(isCompanionEnabled({ config: {} })).toBe(false);
    expect(isCompanionEnabled({ config: { companions_enabled: false } })).toBe(false);
  });

  it('is true only when companions_enabled === true', () => {
    expect(isCompanionEnabled({ companions_enabled: true })).toBe(true);
  });

  it('accepts a full settings row with a nested config', () => {
    expect(isCompanionEnabled({ config: { companions_enabled: true } })).toBe(true);
    expect(isCompanionEnabled({ organization_id: 'x', config: { companions_enabled: true } })).toBe(
      true,
    );
  });
});

describe('companionIdempotencyKey', () => {
  it('builds a companion-namespaced key', () => {
    expect(companionIdempotencyKey('hatch', 'user_123', 'abc')).toBe(
      'companion:hatch:user_123:abc',
    );
  });

  it('always carries the global companion: prefix', () => {
    expect(companionIdempotencyKey('competency_pass', 'u', 'H_ROOK')).toMatch(/^companion:/);
  });

  it('is collision-resistant between kinds for the same owner + ref', () => {
    const owner = 'user_1';
    const ref = 'H_ROOK';
    const hatch = companionIdempotencyKey('hatch', owner, ref);
    const review = companionIdempotencyKey('due_review', owner, ref);
    const pass = companionIdempotencyKey('competency_pass', owner, ref);
    expect(new Set([hatch, review, pass]).size).toBe(3);
  });

  it('distinguishes owners and refs', () => {
    expect(companionIdempotencyKey('hatch', 'a', 'r')).not.toBe(
      companionIdempotencyKey('hatch', 'b', 'r'),
    );
    expect(companionIdempotencyKey('hatch', 'a', 'r1')).not.toBe(
      companionIdempotencyKey('hatch', 'a', 'r2'),
    );
  });

  it('rejects empty / whitespace-only parts', () => {
    expect(() => companionIdempotencyKey('', 'owner', 'ref')).toThrow(/kind/);
    expect(() => companionIdempotencyKey('hatch', '', 'ref')).toThrow(/owner/);
    expect(() => companionIdempotencyKey('hatch', 'owner', '')).toThrow(/ref/);
    expect(() => companionIdempotencyKey('hatch', '  ', 'ref')).toThrow(/owner/);
  });
});
