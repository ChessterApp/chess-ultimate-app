import { describe, expect, it } from 'vitest';
import {
  DEFAULT_RANKS,
  XP_PER_LESSON,
  computeDailyStreak,
  deriveProfile,
  deriveXpFromCompletions,
} from '../derived';

describe('deriveXpFromCompletions', () => {
  it('is 10 XP per completed lesson', () => {
    expect(XP_PER_LESSON).toBe(10);
    expect(deriveXpFromCompletions(0)).toBe(0);
    expect(deriveXpFromCompletions(1)).toBe(10);
    expect(deriveXpFromCompletions(7)).toBe(70);
  });

  it('guards against negative / non-finite input', () => {
    expect(deriveXpFromCompletions(-3)).toBe(0);
    expect(deriveXpFromCompletions(NaN)).toBe(0);
    expect(deriveXpFromCompletions(Infinity)).toBe(0);
  });
});

describe('deriveProfile — completions → xp → rank', () => {
  it('maps zero completions to the lowest rank (Pawn)', () => {
    const p = deriveProfile(0);
    expect(p.xp).toBe(0);
    expect(p.rank?.code).toBe('pawn');
    expect(p.rankProgress.pct).toBeGreaterThanOrEqual(0);
  });

  it('crosses the Knight boundary at exactly 10 XP (1 lesson)', () => {
    // Knight floor is 10 XP in the default ladder → 1 completion promotes.
    expect(deriveProfile(0).rank?.code).toBe('pawn');
    expect(deriveProfile(1).rank?.code).toBe('knight');
  });

  it('spot-checks a higher boundary (Rook at 70 XP = 7 lessons)', () => {
    expect(deriveProfile(6).rank?.code).toBe('bishop'); // 60 XP
    expect(deriveProfile(7).rank?.code).toBe('rook'); // 70 XP
  });

  it('accepts a custom rank ladder', () => {
    const ranks = [
      { code: 'a', name_ru: 'a', name_kk: 'a', name_en: 'A', min_xp: 0, sort_order: 1 },
      { code: 'b', name_ru: 'b', name_kk: 'b', name_en: 'B', min_xp: 100, sort_order: 2 },
    ];
    expect(deriveProfile(5, ranks).rank?.code).toBe('a'); // 50 XP
    expect(deriveProfile(10, ranks).rank?.code).toBe('b'); // 100 XP
  });

  it('exposes the seed ladder as DEFAULT_RANKS', () => {
    expect(DEFAULT_RANKS.map((r) => r.code)).toEqual([
      'pawn', 'knight', 'bishop', 'rook', 'queen', 'king',
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
