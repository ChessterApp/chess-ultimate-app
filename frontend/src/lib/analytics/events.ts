// PRD §11.2 + Phase 1 carryover #6 — centralized PostHog event-name constants.
//
// Source of truth for event names emitted from the wizard, the dashboard
// checklist, and tenant-landing analytics. Any new event added to the
// codebase MUST be registered here.

import posthog from 'posthog-js';

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

  // Whop checkout return (/upgrade/success)
  CHECKOUT_RETURN_VIEWED: 'checkout_return_viewed',
  SUBSCRIPTION_ACTIVATED_CLIENT: 'subscription_activated_client',

  // Tracking plan §4 A — acquisition & onboarding. `user_signed_up` and
  // `level_assigned` are also captured server-side (lib/analytics/server.ts,
  // backend/services/analytics_posthog.py) — same names, single registry.
  //
  // `user_signed_up` dedupe: the Clerk webhook copy (`signup_source: 'server'`)
  // is authoritative. PostHogIdentify adds at most one client copy per device
  // (`signup_source: 'client'`, localStorage-flagged) to carry the browser
  // session's UTMs/referrer. Funnels count persons, so the pair never double
  // counts there; total-count trends must filter `signup_source = server`.
  USER_SIGNED_UP: 'user_signed_up',
  LANDING_CTA_CLICKED: 'landing_cta_clicked',
  LANGUAGE_SWITCHED: 'language_switched',
  ONBOARDING_STARTED: 'onboarding_started',
  ONBOARDING_STEP_COMPLETED: 'onboarding_step_completed',
  ONBOARDING_COMPLETED: 'onboarding_completed',
  PARENT_CONSENT_GIVEN: 'parent_consent_given',
  LEVEL_ASSIGNED: 'level_assigned',

  // Tracking plan §4 B — core value. Activation (§6) = lesson_completed,
  // game_review_completed, or voice_session_ended with duration_s >= 60.
  // Server-captured ones: lesson_*, level_completed, game_review_completed,
  // database_* (Flask), coach_message_sent (Next API).
  LESSON_STARTED: 'lesson_started',
  LESSON_COMPLETED: 'lesson_completed',
  LEVEL_COMPLETED: 'level_completed',
  GAME_REVIEW_REQUESTED: 'game_review_requested',
  GAME_REVIEW_COMPLETED: 'game_review_completed',
  COACH_MESSAGE_SENT: 'coach_message_sent',
  VOICE_SESSION_STARTED: 'voice_session_started',
  VOICE_SESSION_ENDED: 'voice_session_ended',
  BOT_GAME_STARTED: 'bot_game_started',
  BOT_GAME_FINISHED: 'bot_game_finished',
  PUZZLE_RUSH_STARTED: 'puzzle_rush_started',
  PUZZLE_RUSH_FINISHED: 'puzzle_rush_finished',
  TUG_OF_WAR_STARTED: 'tug_of_war_started',
  TUG_OF_WAR_FINISHED: 'tug_of_war_finished',
  DATABASE_CREATED: 'database_created',
  DATABASE_SHARED: 'database_shared',
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
  'phone',
  'dob',
  'transcript',
  'message',
  'content',
] as const;

/** Key prefixes dropped wholesale (birthday, birth_date, birthdate, …). */
export const PII_DENYLIST_PREFIXES: readonly string[] = ['birth'] as const;

function isPiiKey(key: string): boolean {
  const k = key.toLowerCase();
  return PII_DENYLIST.includes(k) || PII_DENYLIST_PREFIXES.some((p) => k.startsWith(p));
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/**
 * Drop any PII/raw-chess-text keys from a tracked-event prop bag. Nested
 * objects (e.g. `$set` / `$set_once` person props) are scrubbed too.
 */
export function stripPii(
  props?: Record<string, unknown>,
): Record<string, unknown> | undefined {
  if (!props) return props;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(props)) {
    if (isPiiKey(k)) continue;
    out[k] = isPlainObject(v) ? stripPii(v) : v;
  }
  return out;
}

export type AnalyticsEvent =
  (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

/**
 * `$set` person properties on the signed-in user. Goes through identify() so it
 * works right after sign-up, before PostHogIdentify's own effect has run (and
 * because `$set` on an anonymous event is dropped under identified_only).
 */
export function setPersonProperties(userId: string, props: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  try {
    posthog.identify(userId, stripPii(props));
  } catch {
    // swallow — analytics never breaks the call site
  }
}

/**
 * Thin wrapper around posthog.capture so call sites never touch the SDK
 * directly. No-op during SSR; before init (or with no key configured) the
 * SDK itself drops the call.
 */
export function track(event: AnalyticsEvent, props?: Record<string, unknown>): void {
  if (typeof window === 'undefined') return;
  try {
    posthog.capture(event, stripPii(props));
  } catch {
    // swallow — analytics never breaks the call site
  }
}
