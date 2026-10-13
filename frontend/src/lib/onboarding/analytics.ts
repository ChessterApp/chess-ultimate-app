/**
 * Onboarding-funnel analytics helpers (tracking plan §4 A). Pure, so the
 * event shapes are unit-testable apart from the 1.4k-line wizard.
 *
 * `answer_bucket` is ALWAYS an enum-like bucket — never free text. The only
 * free-text answer in the funnel (the Chess.com/Lichess username) is reduced
 * to "provided".
 */

export const ONBOARDING_STEP_NAMES: Record<number, string> = {
  1: 'welcome',
  2: 'attribution',
  3: 'experience',
  4: 'platform',
  5: 'username',
  6: 'rating',
  7: 'focus_areas',
  8: 'challenge',
  9: 'practice_time',
  10: 'goal',
  11: 'timeline',
  12: 'puzzle',
  13: 'skill_profile',
  14: 'building_plan',
  15: 'opening_dna',
  16: 'custom_plan',
};

/** Option keys are camelCase identifiers; anything else collapses to "other". */
function enumOnly(v: unknown): string | undefined {
  if (typeof v !== 'string' || !v) return undefined;
  return /^[A-Za-z0-9_]{1,32}$/.test(v) ? v : 'other';
}

function ratingBand(a: Record<string, unknown>): string {
  if (a.noRating === true) return 'none';
  const online = Number(a.onlineRating) || 0;
  const rating = online > 0 ? online : Number(a.eloRating) || 0;
  if (rating < 800) return 'lt_800';
  if (rating < 1200) return '800_1199';
  if (rating < 1600) return '1200_1599';
  return '1600_plus';
}

export function answerBucket(step: number, a: Record<string, unknown>): string | undefined {
  switch (step) {
    case 2:
      return enumOnly(a.attribution);
    case 3:
      return enumOnly(a.experience);
    case 4:
      return enumOnly(a.platform);
    case 5:
      return a.platformUsername ? 'provided' : 'skipped';
    case 6:
      return ratingBand(a);
    case 7:
      return Array.isArray(a.focusAreas)
        ? a.focusAreas.map(enumOnly).filter(Boolean).sort().join(',') || undefined
        : undefined;
    case 8:
      return enumOnly(a.challenge);
    case 9:
      return enumOnly(a.practiceTime);
    case 10:
      return enumOnly(a.goal);
    case 11:
      return enumOnly(a.timeline);
    default:
      return undefined;
  }
}

export function stepCompletedProps(step: number, answers: Record<string, unknown>) {
  const bucket = answerBucket(step, answers);
  return {
    step_index: step,
    step_name: ONBOARDING_STEP_NAMES[step] ?? `step_${step}`,
    ...(bucket ? { answer_bucket: bucket } : {}),
  };
}

/** How the visitor reached the funnel: paid/UTM traffic, the landing page, or direct. */
export function onboardingEntry(search: string, referrer: string, origin: string): 'ad' | 'landing' | 'direct' {
  const params = new URLSearchParams(search);
  if (params.get('utm_source') || params.get('utm_medium') || params.get('fbclid') || params.get('gclid')) {
    return 'ad';
  }
  if (referrer && referrer.startsWith(origin)) return 'landing';
  return 'direct';
}
