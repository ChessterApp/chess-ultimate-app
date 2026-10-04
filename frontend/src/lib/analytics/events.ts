// PRD §11.2 + Phase 1 carryover #6 — centralized PostHog event-name constants.
//
// Source of truth for event names emitted from the wizard, the dashboard
// checklist, and tenant-landing analytics. Any new event added to the
// codebase MUST be registered here.

export const ANALYTICS_EVENTS = {
  // Wizard step transitions
  SCHOOL_ONBOARDING_STARTED: 'school_onboarding_started',
  SCHOOL_ONBOARDING_STEP_VIEWED: 'school_onboarding_step_viewed',
  SCHOOL_ONBOARDING_STEP_ADVANCED: 'school_onboarding_step_advanced',
  SCHOOL_ONBOARDING_COMPLETED: 'school_onboarding_completed',

  // Step-specific events
  SCHOOL_ONBOARDING_PLAN_SELECTED: 'school_onboarding_plan_selected',
  SCHOOL_ONBOARDING_PAYMENT_INITIATED: 'school_onboarding_payment_initiated',
  SCHOOL_ONBOARDING_PAYMENT_COMPLETED: 'school_onboarding_payment_completed',
  SCHOOL_ONBOARDING_LOGO_UPLOADED: 'school_onboarding_logo_uploaded',
  SCHOOL_ONBOARDING_COLORS_AUTODETECTED: 'school_onboarding_colors_autodetected',
  SCHOOL_ONBOARDING_COLORS_OVERRIDDEN: 'school_onboarding_colors_overridden',

  // CSV importer
  SCHOOL_ONBOARDING_CSV_PARSED: 'school_onboarding_csv_parsed',
  SCHOOL_ONBOARDING_CSV_IMPORTED: 'school_onboarding_csv_imported',
  SCHOOL_ONBOARDING_INVITES_SENT: 'school_onboarding_invites_sent',

  // Dashboard checklist
  ONBOARDING_CHECKLIST_VIEWED: 'onboarding_checklist_viewed',
  ONBOARDING_CHECKLIST_ITEM_COMPLETED: 'onboarding_checklist_item_completed',
  ONBOARDING_CHECKLIST_COMPLETED: 'onboarding_checklist_completed',

  // Custom domain
  CUSTOM_DOMAIN_ADDED: 'custom_domain_added',
  CUSTOM_DOMAIN_VERIFIED: 'custom_domain_verified',
  CUSTOM_DOMAIN_FAILED: 'custom_domain_failed',

  // Sender domain
  SENDER_DOMAIN_ADDED: 'sender_domain_added',
  SENDER_DOMAIN_VERIFIED: 'sender_domain_verified',

  // Play — regression guard: a bot move was needed while the local engine
  // wasn't ready yet (Maia served from the server fallback, or Stockfish still
  // initializing). Should be rare; a spike means readiness/persistence regressed.
  PLAY_ENGINE_WAIT: 'play_engine_wait',

  // Companion (spec §13) — fired only from the flag-gated companion surfaces.
  // Props carry stable IDs + version + cohort; NEVER PII or raw chess text
  // (names/FENs/solutions are stripped by stripPii below).
  COMPANION_EGG_RECEIVED: 'egg_received',
  COMPANION_COMPETENCY_ATTEMPTED: 'competency_attempted',
  COMPANION_COMPETENCY_PASSED: 'competency_passed',
  COMPANION_HATCH_ELIGIBLE: 'hatch_eligible',
  COMPANION_HATCHED: 'companion_hatched',
  COMPANION_NAMED: 'companion_named',
  COMPANION_QUEST_STARTED: 'quest_started',
  COMPANION_QUEST_COMPLETED: 'quest_completed',
  COMPANION_REVIEW_COMPLETED: 'review_completed',
  COMPANION_MASTERY_UPDATED: 'mastery_updated',
  COMPANION_REWARD_GRANTED: 'reward_granted',
  COMPANION_WEEKLY_GOAL_UPDATED: 'weekly_goal_updated',
} as const;

/**
 * Prop keys that could carry PII or raw chess text (spec §13: "Avoid
 * unnecessary personal text in analytics"). These are stripped from EVERY
 * tracked event by construction — companion names, FEN/PGN/moves, solutions,
 * prompts, and identifiers never reach PostHog. Keep names/IDs that are stable
 * and non-identifying (competency codes, quest ids, versions) out of this list.
 */
export const PII_DENYLIST: readonly string[] = [
  'name',
  'companion_name',
  'email',
  'fen',
  'pgn',
  'san',
  'uci',
  'move',
  'moves',
  'squares',
  'placement',
  'solution',
  'prompt',
  'hint',
  'text',
] as const;

/** Drop any PII/raw-chess-text keys from a tracked-event prop bag. */
export function stripPii(
  props?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!props) return props;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    if (PII_DENYLIST.includes(k.toLowerCase())) continue;
    out[k] = v;
  }
  return out;
}

export type AnalyticsEvent =
  (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

/**
 * Thin wrapper around window.posthog.capture so call sites don't have to
 * null-check the global. No-op when PostHog hasn't loaded yet (SSR / before
 * instrumentation-client mounts).
 */
export function track(event: AnalyticsEvent, props?: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  const ph = (window as unknown as {
    posthog?: { capture: (e: string, p?: Record<string, unknown>) => void };
  }).posthog;
  if (!ph) return;
  try {
    ph.capture(event, stripPii(props));
  } catch {
    // swallow — analytics never breaks the call site
  }
}
