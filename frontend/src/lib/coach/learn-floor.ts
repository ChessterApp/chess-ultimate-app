/**
 * The student's Chess Empire level for the coach (tester 20.11, item 12): /learn opens a CE roster student's courses up
 * to their school level, and the coach offers and opens only the lessons /learn opens (hermes/src/learn_access.py).
 *
 * The level is the student's, not the address's: the app's «Обучение» reads it from the school's site whatever host
 * the coach is asked through, so the coach does too — by the user alone (`getMembershipStateForUser`), through the
 * same rule as /learn (`floorFromMembership`). It goes to Hermes as the `x-learn-floor` header from the proxies and in
 * the direct path's pass — never from the page. Kept 10 minutes per student (a school level changes rarely; the
 * lookup is a database read and a call to the school's system). Any failure: no floor (progress alone decides).
 */
import 'server-only';
import { getMembershipStateForUser } from '@/lib/chess-empire-member';
import { floorFromMembership } from '@/lib/learn-ce-floor';

const KEEP_MS = 10 * 60_000;
const MAX_ENTRIES = 5_000;
const kept = new Map<string, { floor: number | undefined; until: number }>();
const pending = new Map<string, Promise<number | undefined>>();

export async function coachLearnFloor(userId: string): Promise<number | undefined> {
  const now = Date.now();
  const hit = kept.get(userId);
  if (hit && hit.until > now) return hit.floor;
  const inFlight = pending.get(userId);
  if (inFlight) return inFlight;
  const run = (async () => {
    let floor: number | undefined;
    try {
      floor = await floorFromMembership(await getMembershipStateForUser(userId));
    } catch {
      floor = undefined;
    }
    if (kept.size >= MAX_ENTRIES) kept.clear();
    kept.set(userId, { floor, until: Date.now() + KEEP_MS });
    return floor;
  })().finally(() => pending.delete(userId));
  pending.set(userId, run);
  return run;
}

/** The header the proxies send it in (nothing when there is no floor). */
export function learnFloorHeader(floor: number | undefined): Record<string, string> {
  return floor ? { 'x-learn-floor': String(floor) } : {};
}

/** Tests only. */
export function resetCoachLearnFloor(): void {
  kept.clear();
  pending.clear();
}
