/**
 * @vitest-environment node
 *
 * Pure-rules unit tests for the SM-2 review scheduler (Phase 4). The clock is
 * INJECTED so time advances deterministically — no DB, no real time. Asserts the
 * spec §6.3 ladder (1→3→7→14) progresses on success and resets to rung 1 on a
 * miss, and that the pull-model "due" predicate / occurrence marker behave.
 */
import { describe, it, expect } from 'vitest';
import {
  DEFAULT_REVIEW_LADDER,
  dueMarker,
  isDue,
  nextIntervalDays,
  normalizeLadder,
  rungForInterval,
  scheduleReview,
  WATCHTOWER_NODE_FAMILIES,
  WATCHTOWER_TOTAL_NODES,
  isWatchtowerNode,
} from '../review-rules';

const DAY = 86_400_000;

describe('nextIntervalDays — fixed ladder progression', () => {
  it('advances 0→1→3→7→14 on consecutive correct reviews, capping at 14', () => {
    expect(nextIntervalDays(0, true)).toBe(1);
    expect(nextIntervalDays(1, true)).toBe(3);
    expect(nextIntervalDays(3, true)).toBe(7);
    expect(nextIntervalDays(7, true)).toBe(14);
    expect(nextIntervalDays(14, true)).toBe(14); // caps at the last rung
  });

  it('resets to rung 1 on a miss, from any rung', () => {
    for (const cur of [0, 1, 3, 7, 14]) {
      expect(nextIntervalDays(cur, false)).toBe(1);
    }
  });
});

describe('scheduleReview — injected clock advances the full ladder', () => {
  it('walks 1→3→7→14 days across advancing time', () => {
    let now = new Date('2026-01-01T00:00:00.000Z');
    let interval = 0;

    const step = (correct: boolean) => {
      const s = scheduleReview({ intervalDays: interval, correct, now });
      interval = s.intervalDays;
      return s;
    };

    const s1 = step(true);
    expect(s1.intervalDays).toBe(1);
    expect(s1.nextReviewAt).toBe(new Date(now.getTime() + 1 * DAY).toISOString());

    now = new Date('2026-01-02T00:00:00.000Z'); // time moves forward
    const s2 = step(true);
    expect(s2.intervalDays).toBe(3);
    expect(s2.nextReviewAt).toBe(new Date(now.getTime() + 3 * DAY).toISOString());

    now = new Date('2026-01-05T00:00:00.000Z');
    const s3 = step(true);
    expect(s3.intervalDays).toBe(7);

    now = new Date('2026-01-12T00:00:00.000Z');
    const s4 = step(true);
    expect(s4.intervalDays).toBe(14);
    expect(s4.nextReviewAt).toBe(new Date(now.getTime() + 14 * DAY).toISOString());
  });

  it('a miss mid-ladder resets to a 1-day interval', () => {
    const now = new Date('2026-02-01T00:00:00.000Z');
    const s = scheduleReview({ intervalDays: 7, correct: false, now });
    expect(s.intervalDays).toBe(1);
    expect(s.nextReviewAt).toBe(new Date(now.getTime() + 1 * DAY).toISOString());
  });

  it('honours a ladder supplied from DATA (not hardcoded)', () => {
    const now = new Date('2026-03-01T00:00:00.000Z');
    const ladder = [2, 5, 9];
    expect(scheduleReview({ intervalDays: 0, correct: true, now, ladder }).intervalDays).toBe(2);
    expect(scheduleReview({ intervalDays: 2, correct: true, now, ladder }).intervalDays).toBe(5);
    expect(scheduleReview({ intervalDays: 9, correct: true, now, ladder }).intervalDays).toBe(9);
  });
});

describe('normalizeLadder', () => {
  it('falls back to the spec default for junk', () => {
    expect(normalizeLadder(undefined)).toEqual([...DEFAULT_REVIEW_LADDER]);
    expect(normalizeLadder('nope')).toEqual([...DEFAULT_REVIEW_LADDER]);
    expect(normalizeLadder([])).toEqual([...DEFAULT_REVIEW_LADDER]);
  });

  it('keeps only strictly-ascending positive integers', () => {
    expect(normalizeLadder([1, 3, 7, 14])).toEqual([1, 3, 7, 14]);
    expect(normalizeLadder([1, 1, 2, 0, -3, 5])).toEqual([1, 2, 5]);
  });
});

describe('rungForInterval', () => {
  it('maps an interval to its 1-based rung (0 = never reviewed)', () => {
    expect(rungForInterval(0)).toBe(0);
    expect(rungForInterval(1)).toBe(1);
    expect(rungForInterval(3)).toBe(2);
    expect(rungForInterval(7)).toBe(3);
    expect(rungForInterval(14)).toBe(4);
  });
});

describe('isDue — pull model (next_review_at <= now OR null)', () => {
  const now = new Date('2026-01-10T00:00:00.000Z');
  it('null / malformed is due immediately', () => {
    expect(isDue(null, now)).toBe(true);
    expect(isDue(undefined, now)).toBe(true);
    expect(isDue('not-a-date', now)).toBe(true);
  });
  it('past is due, future is not', () => {
    expect(isDue('2026-01-09T00:00:00.000Z', now)).toBe(true);
    expect(isDue('2026-01-10T00:00:00.000Z', now)).toBe(true); // == now
    expect(isDue('2026-01-11T00:00:00.000Z', now)).toBe(false);
  });
});

describe('dueMarker — one idempotency marker per due occurrence', () => {
  it('is "initial" for the first-ever (null) review', () => {
    expect(dueMarker(null)).toBe('initial');
  });
  it('is the UTC date of the occurrence that became due', () => {
    expect(dueMarker('2026-01-11T09:30:00.000Z')).toBe('2026-01-11');
  });
  it('distinct occurrences ⇒ distinct markers (so a new rung can re-reward)', () => {
    expect(dueMarker('2026-01-11T00:00:00.000Z')).not.toBe(dueMarker('2026-01-14T00:00:00.000Z'));
  });
});

describe('Watchtower node metadata', () => {
  it('exposes the six chapter families', () => {
    expect(WATCHTOWER_NODE_FAMILIES).toEqual(['W01', 'W02', 'W03', 'W04', 'W05', 'W06']);
    expect(WATCHTOWER_TOTAL_NODES).toBe(6);
  });
  it('recognises only valid node families', () => {
    expect(isWatchtowerNode('W01')).toBe(true);
    expect(isWatchtowerNode('W07')).toBe(false);
    expect(isWatchtowerNode('H_ROOK')).toBe(false);
  });
});
