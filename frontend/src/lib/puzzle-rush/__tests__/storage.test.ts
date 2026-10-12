/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  loadGuestBests, loadLastMode, recordGuestScore, saveLastMode, hasSeenRules, markRulesSeen, localStore,
} from '../storage';

beforeEach(() => {
  localStorage.clear();
});

describe('mode preselect', () => {
  it('falls back to 5 min when nothing was played', () => {
    expect(loadLastMode()).toBe('5min');
  });

  it('preselects the last-played mode', () => {
    saveLastMode('survival');
    expect(loadLastMode()).toBe('survival');
  });

  it('ignores a corrupt stored value', () => {
    localStorage.setItem('puzzleRush.lastMode', 'blitz');
    expect(loadLastMode()).toBe('5min');
  });
});

describe('rules + outbox store', () => {
  it('remembers that the rules were seen', () => {
    expect(hasSeenRules()).toBe(false);
    markRulesSeen();
    expect(hasSeenRules()).toBe(true);
  });

  it('localStore is a thin localStorage wrapper', () => {
    const store = localStore();
    store.setItem('k', 'v');
    expect(localStorage.getItem('k')).toBe('v');
    expect(store.getItem('k')).toBe('v');
    store.removeItem('k');
    expect(store.getItem('k')).toBeNull();
  });
});

describe('guest bests (on-device)', () => {
  const day1 = new Date(2026, 9, 12, 10);
  const day2 = new Date(2026, 9, 13, 9);

  it('tracks top score and best today per mode; zero is never a PB', () => {
    expect(recordGuestScore('3min', 0, day1)).toBe(false);
    expect(recordGuestScore('3min', 8, day1)).toBe(true);
    expect(recordGuestScore('3min', 5, day1)).toBe(false);
    expect(recordGuestScore('3min', 8, day1)).toBe(false); // ties are not a new PB
    const b = loadGuestBests(day1);
    expect(b['3min']).toMatchObject({ top_score: 8, best_today: 8 });
    expect(b['5min']).toMatchObject({ top_score: null, best_today: null });
  });

  it('resets Best Today on a new local day', () => {
    recordGuestScore('survival', 12, day1);
    expect(loadGuestBests(day2).survival).toMatchObject({ top_score: 12, best_today: null });
    recordGuestScore('survival', 4, day2);
    expect(loadGuestBests(day2).survival).toMatchObject({ top_score: 12, best_today: 4 });
  });
});
