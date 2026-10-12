/**
 * On-device Puzzle Rush state (web): last-played mode, the first-visit rules
 * flag, guest bests (never sent anywhere) and the store behind the finished-run
 * outbox.
 */

import type { KeyValueStore } from './outbox';
import { RUSH_MODES, type ModeBests, type RushMode } from './types';

const LAST_MODE_KEY = 'puzzleRush.lastMode';
const RULES_SEEN_KEY = 'puzzleRush.rulesSeen';
const GUEST_BESTS_KEY = 'puzzleRush.guestBests';

export const DEFAULT_MODE: RushMode = '5min';

function read(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(storage: Storage | undefined, key: string, value: string | null) {
  try {
    if (value === null) storage?.removeItem(key);
    else storage?.setItem(key, value);
  } catch {
    // Private mode / quota: on-device state is best-effort.
  }
}

const local = () => (typeof window === 'undefined' ? undefined : window.localStorage);

/** localStorage as the outbox store; a no-op store where it's unavailable. */
export function localStore(): KeyValueStore {
  return {
    getItem: (key) => read(local(), key),
    setItem: (key, value) => write(local(), key, value),
    removeItem: (key) => write(local(), key, null),
  };
}

/** Last-played mode, falling back to 5 min (§7.1). */
export function loadLastMode(): RushMode {
  const v = read(local(), LAST_MODE_KEY);
  return RUSH_MODES.includes(v as RushMode) ? (v as RushMode) : DEFAULT_MODE;
}

export function saveLastMode(mode: RushMode) {
  write(local(), LAST_MODE_KEY, mode);
}

export function hasSeenRules(): boolean {
  return read(local(), RULES_SEEN_KEY) === '1';
}

export function markRulesSeen() {
  write(local(), RULES_SEEN_KEY, '1');
}

interface GuestBest {
  top: number | null;
  today: number | null;
  /** Local calendar day `today` belongs to (YYYY-MM-DD). */
  day: string | null;
}

export function localDay(now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function loadGuestRaw(): Partial<Record<RushMode, GuestBest>> {
  try {
    return JSON.parse(read(local(), GUEST_BESTS_KEY) || '{}');
  } catch {
    return {};
  }
}

/** Guest bests in the same shape as the server's `/bests`. */
export function loadGuestBests(now: Date = new Date()): Record<RushMode, ModeBests> {
  const raw = loadGuestRaw();
  const day = localDay(now);
  const out = {} as Record<RushMode, ModeBests>;
  for (const mode of RUSH_MODES) {
    const b = raw[mode];
    out[mode] = {
      top_score: b?.top ?? null,
      top_run_id: null,
      achieved_at: null,
      best_today: b && b.day === day ? b.today : null,
    };
  }
  return out;
}

/** Record a finished guest run; returns true when it beat the on-device best. */
export function recordGuestScore(mode: RushMode, score: number, now: Date = new Date()): boolean {
  const raw = loadGuestRaw();
  const day = localDay(now);
  const prev = raw[mode] ?? { top: null, today: null, day: null };
  const isPb = score > 0 && score > (prev.top ?? 0);
  const todayPrev = prev.day === day ? prev.today ?? 0 : 0;
  raw[mode] = {
    top: Math.max(prev.top ?? 0, score),
    today: Math.max(todayPrev, score),
    day,
  };
  write(local(), GUEST_BESTS_KEY, JSON.stringify(raw));
  return isPb;
}
