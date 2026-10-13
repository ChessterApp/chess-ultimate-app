/**
 * Cross-signup persistence for the anonymous consumer onboarding funnel.
 *
 * The funnel (`/onboarding`) collects answers anonymously, then sends the user
 * to Clerk sign-up. These answers must survive that redirect so the
 * `/onboarding/complete` claim page can attach them to the freshly-created
 * account. Two carriers, belt-and-suspenders:
 *   1. localStorage (primary) — same-origin, survives the sign-up round-trip.
 *   2. Clerk `unsafeMetadata.onboardingAnswers` (backup) — written on the
 *      sign-up page, read by the claim page if localStorage was cleared
 *      (e.g. a cross-device signup). Mirrors the proven `inviteJwt` pattern.
 *
 * `gameData` (and the transient `startFetch` flag) are intentionally excluded —
 * gameData can be large and is re-derivable; it is never needed server-side.
 */

export const PENDING_ANSWERS_KEY = "chesster_onboarding_pending";

// Compact, backend-facing subset (camelCase — matches `_pick` in
// backend/routes/onboarding.py `save_onboarding_profile`).
export interface PendingOnboardingAnswers {
  attribution?: string;
  experience?: string;
  platform?: string;
  platformUsername?: string;
  onlineRating?: number;
  eloRating?: number;
  noRating?: boolean;
  focusAreas?: string[];
  challenge?: string;
  practiceTime?: string;
  goal?: string;
  timeline?: string;
}

/** Strip transient/bulky fields down to the backend-facing answer set. */
export function compactAnswers(answers: Record<string, unknown> | null | undefined): PendingOnboardingAnswers {
  const a = answers || {};
  const out: PendingOnboardingAnswers = {
    attribution: a.attribution as string | undefined,
    experience: a.experience as string | undefined,
    platform: a.platform as string | undefined,
    platformUsername: a.platformUsername as string | undefined,
    onlineRating: a.onlineRating as number | undefined,
    eloRating: a.eloRating as number | undefined,
    noRating: a.noRating as boolean | undefined,
    focusAreas: Array.isArray(a.focusAreas) ? (a.focusAreas as string[]) : undefined,
    challenge: a.challenge as string | undefined,
    practiceTime: a.practiceTime as string | undefined,
    goal: a.goal as string | undefined,
    timeline: a.timeline as string | undefined,
  };
  return out;
}

/** Persist the funnel answers (compacted) right before the sign-up redirect. */
export function writePendingAnswers(answers: Record<string, unknown> | null | undefined): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(PENDING_ANSWERS_KEY, JSON.stringify(compactAnswers(answers)));
  } catch {
    /* storage disabled / quota — the unsafeMetadata backup still carries them */
  }
}

/** Read the persisted answers, or null if none / unreadable. */
export function readPendingAnswers(): PendingOnboardingAnswers | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(PENDING_ANSWERS_KEY);
    return raw ? (JSON.parse(raw) as PendingOnboardingAnswers) : null;
  } catch {
    return null;
  }
}

/** Clear the persisted answers after a successful claim. */
export function clearPendingAnswers(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(PENDING_ANSWERS_KEY);
  } catch {
    /* non-fatal */
  }
}
