/**
 * Tests for the coach-home roster aggregation (computeCoachStats / hasRazryad).
 * Focus: razryad counting edge cases ("none", empty, whitespace, casing) and
 * league breakdown ordering.
 */
import { describe, it, expect } from 'vitest';
import type { CEActiveStudent } from '../chess-empire-client';
import { computeCoachStats, hasRazryad } from '../empire-coach-stats';

function student(over: Partial<CEActiveStudent>): CEActiveStudent {
  return {
    id: Math.random().toString(36).slice(2),
    first_name: 'A',
    last_name: 'B',
    status: 'active',
    branch_id: 'br-1',
    coach_id: 'co-1',
    current_razryad: null,
    current_league: null,
    ...over,
  };
}

describe('hasRazryad', () => {
  it('is false for null / undefined / empty / whitespace / "none"', () => {
    expect(hasRazryad(null)).toBe(false);
    expect(hasRazryad(undefined)).toBe(false);
    expect(hasRazryad('')).toBe(false);
    expect(hasRazryad('   ')).toBe(false);
    expect(hasRazryad('none')).toBe(false);
    expect(hasRazryad('None')).toBe(false);
    expect(hasRazryad(' NONE ')).toBe(false);
  });

  it('is true for a real razryad value', () => {
    expect(hasRazryad('1st')).toBe(true);
    expect(hasRazryad('4th')).toBe(true);
    expect(hasRazryad(' 2nd ')).toBe(true);
  });
});

describe('computeCoachStats', () => {
  it('returns all-zero/empty for an empty roster', () => {
    expect(computeCoachStats([])).toEqual({
      total: 0,
      withRazryad: 0,
      leagueBreakdown: [],
    });
  });

  it('counts total, razryad (excluding none/empty), and league breakdown', () => {
    const roster: CEActiveStudent[] = [
      student({ current_razryad: '3rd', current_league: 'A' }),
      student({ current_razryad: 'none', current_league: 'A' }),
      student({ current_razryad: '', current_league: 'B' }),
      student({ current_razryad: null, current_league: 'B' }),
      student({ current_razryad: '1st', current_league: 'B' }),
      student({ current_razryad: '2nd', current_league: null }),
    ];
    const stats = computeCoachStats(roster);
    expect(stats.total).toBe(6);
    // '3rd', '1st', '2nd' count; 'none', '', null do not.
    expect(stats.withRazryad).toBe(3);
    // League B (3) before A (2); null/empty leagues excluded.
    expect(stats.leagueBreakdown).toEqual([
      { league: 'B', count: 3 },
      { league: 'A', count: 2 },
    ]);
  });

  it('breaks league count ties alphabetically', () => {
    const roster: CEActiveStudent[] = [
      student({ current_league: 'C' }),
      student({ current_league: 'A' }),
    ];
    expect(computeCoachStats(roster).leagueBreakdown).toEqual([
      { league: 'A', count: 1 },
      { league: 'C', count: 1 },
    ]);
  });
});
