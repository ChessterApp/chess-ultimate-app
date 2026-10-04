/**
 * @vitest-environment node
 *
 * Companion Phase 5 — pure weekly-goal rules, with an INJECTED clock so time
 * moves deterministically (mirrors review-rules.test.ts). Covers week-boundary
 * reset, meaningful-day counting (login-only does NOT count), and target
 * clamping. R2 (no gating / no penalty) is asserted separately in
 * r2-invariant.test.ts.
 */
import { describe, it, expect } from 'vitest';
import {
  DEFAULT_WEEKLY_GOAL_TARGET,
  MAX_WEEKLY_GOAL_TARGET,
  MIN_WEEKLY_GOAL_TARGET,
  clampTarget,
  computeGoalProgress,
  countMeaningfulDays,
  isMeaningfulKind,
  isValidTarget,
  utcDayKey,
  weekBounds,
  weekStart,
} from '../goal-rules';

const DAY = 86_400_000;
// A fixed instant mid-week; all cases anchor to weekStart(now) so they are
// independent of which weekday the literal happens to fall on.
const NOW = new Date('2026-10-07T12:00:00.000Z');

describe('weekStart / weekBounds', () => {
  it('starts the week on Monday 00:00 UTC', () => {
    const ws = weekStart(NOW);
    expect(ws.getUTCHours()).toBe(0);
    expect(ws.getUTCMinutes()).toBe(0);
    expect(ws.getUTCDay()).toBe(1); // Monday
    expect(ws.getTime()).toBeLessThanOrEqual(NOW.getTime());
    expect(NOW.getTime() - ws.getTime()).toBeLessThan(7 * DAY);
  });

  it('has an exclusive end exactly 7 days after the start', () => {
    const { start, end } = weekBounds(NOW);
    expect(end.getTime() - start.getTime()).toBe(7 * DAY);
  });
});

describe('isMeaningfulKind', () => {
  it('counts learning / assessment / review / placement / game', () => {
    for (const k of ['learning', 'assessment', 'review', 'placement', 'game']) {
      expect(isMeaningfulKind(k)).toBe(true);
    }
  });
  it('does NOT count a login or reward claim (spec line 1200)', () => {
    expect(isMeaningfulKind('login')).toBe(false);
    expect(isMeaningfulKind('reward')).toBe(false);
    expect(isMeaningfulKind('')).toBe(false);
    expect(isMeaningfulKind(undefined)).toBe(false);
  });
});

describe('countMeaningfulDays', () => {
  const ws = weekStart(NOW);
  const at = (days: number, hours = 9) => new Date(ws.getTime() + days * DAY + hours * 3600_000).toISOString();

  it('counts DISTINCT meaningful days within the current week', () => {
    const activities = [
      { kind: 'learning', at: at(0, 9) },
      { kind: 'review', at: at(0, 20) }, // same day as above ⇒ not double-counted
      { kind: 'game', at: at(2) },
    ];
    expect(countMeaningfulDays(activities, NOW)).toBe(2);
  });

  it('ignores login-only activity (attendance never counts)', () => {
    const activities = [
      { kind: 'login', at: at(0) },
      { kind: 'login', at: at(1) },
      { kind: 'reward', at: at(2) },
    ];
    expect(countMeaningfulDays(activities, NOW)).toBe(0);
  });

  it('resets at the week boundary — last week does not count this week', () => {
    const lastWeek = [{ kind: 'learning', at: at(-1) }]; // Sunday before this Monday
    expect(countMeaningfulDays(lastWeek, NOW)).toBe(0);

    // The SAME activity counts when "now" is inside its week.
    const nowLastWeek = new Date(ws.getTime() - 2 * DAY);
    expect(countMeaningfulDays(lastWeek, nowLastWeek)).toBe(1);
  });

  it('ignores activity in a future week', () => {
    expect(countMeaningfulDays([{ kind: 'learning', at: at(7) }], NOW)).toBe(0);
  });

  it('tolerates malformed timestamps', () => {
    expect(countMeaningfulDays([{ kind: 'learning', at: 'not-a-date' }], NOW)).toBe(0);
  });
});

describe('clampTarget / isValidTarget', () => {
  it('clamps into [1,7] and floors fractional values', () => {
    expect(clampTarget(0)).toBe(MIN_WEEKLY_GOAL_TARGET);
    expect(clampTarget(99)).toBe(MAX_WEEKLY_GOAL_TARGET);
    expect(clampTarget(3)).toBe(3);
    expect(clampTarget(3.9)).toBe(3);
  });
  it('falls back for malformed input', () => {
    expect(clampTarget('nope')).toBe(DEFAULT_WEEKLY_GOAL_TARGET);
    expect(clampTarget(undefined, 5)).toBe(5);
  });
  it('validates the sane 1..7 integer bounds', () => {
    expect(isValidTarget(1)).toBe(true);
    expect(isValidTarget(7)).toBe(true);
    expect(isValidTarget(0)).toBe(false);
    expect(isValidTarget(8)).toBe(false);
    expect(isValidTarget(3.5)).toBe(false);
  });
});

describe('computeGoalProgress', () => {
  const ws = weekStart(NOW);
  it('reports target + current-week progress + met', () => {
    const activities = [
      { kind: 'learning', at: new Date(ws.getTime() + 1 * DAY).toISOString() },
      { kind: 'review', at: new Date(ws.getTime() + 3 * DAY).toISOString() },
      { kind: 'game', at: new Date(ws.getTime() + 5 * DAY).toISOString() },
    ];
    const r = computeGoalProgress({ target: 3, activities, now: NOW });
    expect(r).toMatchObject({ target: 3, progress: 3, met: true });
    expect(r.week_start).toBe(ws.toISOString());
    expect(utcDayKey(ws)).toBe(ws.toISOString().slice(0, 10));
  });

  it('a zero-activity week is progress 0, met false — never negative', () => {
    const r = computeGoalProgress({ target: 3, activities: [], now: NOW });
    expect(r.progress).toBe(0);
    expect(r.met).toBe(false);
    expect(r.progress).toBeGreaterThanOrEqual(0);
  });
});
