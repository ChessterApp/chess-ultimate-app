import { describe, expect, it } from 'vitest';
import {
  DEFAULT_RANKS,
  computeDailyStreak,
  deriveProfile,
} from '../derived';

describe('deriveProfile — server lesson XP → rank', () => {
  it('maps zero XP to the lowest rank (Pawn)', () => {
    const p = deriveProfile(0);
    expect(p.xp).toBe(0);
    expect(p.rank?.code).toBe('pawn');
    expect(p.rankProgress.pct).toBeGreaterThanOrEqual(0);
  });

  it('uses the server XP as-is (one beginner theory lesson = Knight)', () => {
    expect(deriveProfile(9).rank?.code).toBe('pawn');
    expect(deriveProfile(10).rank?.code).toBe('knight');
    expect(deriveProfile(10).xp).toBe(10);
  });

  it('spot-checks higher boundaries', () => {
    expect(deriveProfile(69).rank?.code).toBe('bishop');
    expect(deriveProfile(70).rank?.code).toBe('rook');
    expect(deriveProfile(300).rank?.code).toBe('king');
  });

  it('guards against negative / non-finite / missing XP', () => {
    expect(deriveProfile(-3).xp).toBe(0);
    expect(deriveProfile(NaN).xp).toBe(0);
    expect(deriveProfile(Infinity).xp).toBe(0);
    expect(deriveProfile(undefined as unknown as number).xp).toBe(0);
  });

  it('accepts a custom rank ladder', () => {
    const ranks = [
      { code: 'a', name_ru: 'a', name_kk: 'a', name_en: 'A', min_xp: 0, sort_order: 1 },
      { code: 'b', name_ru: 'b', name_kk: 'b', name_en: 'B', min_xp: 100, sort_order: 2 },
    ];
    expect(deriveProfile(50, ranks).rank?.code).toBe('a');
    expect(deriveProfile(100, ranks).rank?.code).toBe('b');
  });

  it('keeps the seed ladder thresholds (DEFAULT_RANKS unchanged)', () => {
    expect(DEFAULT_RANKS.map((r) => [r.code, r.min_xp])).toEqual([
      ['pawn', 0], ['knight', 10], ['bishop', 30], ['rook', 70], ['queen', 150], ['king', 300],
    ]);
  });
});

describe('computeDailyStreak — daily streaks from completion dates', () => {
  const TODAY = new Date('2026-09-15T12:00:00Z');

  it('empty history → 0', () => {
    expect(computeDailyStreak([], TODAY)).toBe(0);
  });

  it('a single completion today → 1', () => {
    expect(computeDailyStreak(['2026-09-15'], TODAY)).toBe(1);
  });

  it('three consecutive days ending today → 3', () => {
    expect(computeDailyStreak(['2026-09-13', '2026-09-14', '2026-09-15'], TODAY)).toBe(3);
  });

  it('a gap breaks the streak (counts only the run touching today)', () => {
    // 09-15 + 09-14, then a gap at 09-13, then 09-12 → current run is 2.
    expect(computeDailyStreak(['2026-09-12', '2026-09-14', '2026-09-15'], TODAY)).toBe(2);
  });

  it('completion yesterday but not today still counts the current streak', () => {
    expect(computeDailyStreak(['2026-09-13', '2026-09-14'], TODAY)).toBe(2);
  });

  it('nothing today or yesterday → 0 (streak has lapsed)', () => {
    expect(computeDailyStreak(['2026-09-12', '2026-09-13'], TODAY)).toBe(0);
  });

  it('duplicate same-day completions count once', () => {
    expect(computeDailyStreak(['2026-09-15', '2026-09-15', '2026-09-14'], TODAY)).toBe(2);
  });

  it('normalizes datetime strings to their UTC day', () => {
    expect(
      computeDailyStreak(
        ['2026-09-14T23:30:00Z', '2026-09-15T00:05:00.123Z'],
        TODAY,
      ),
    ).toBe(2);
  });
});
