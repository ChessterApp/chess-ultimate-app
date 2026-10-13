// Server-side PostHog capture for Next API routes (tracking plan §7 / F6).
//
// Authoritative events (signup, coach, voice …) are captured here so ad
// blockers can't drop them. Serverless-safe: one short-lived client per call
// (flushAt 1, flushInterval 0) that is shut down — and therefore flushed —
// before we return. Analytics must never break a request: a missing key or any
// PostHog failure is swallowed.

import 'server-only';
import { PostHog } from 'posthog-node';
import { stripPii, type AnalyticsEvent } from './events';

export const POSTHOG_CAPTURE_HOST = 'https://us.i.posthog.com';

/**
 * Capture `event` for `distinctId` (always the Clerk user id — the parent
 * account). Props go through the same `stripPii` scrub as client events,
 * including nested `$set` / `$set_once` person props.
 */
export async function captureServer(
  distinctId: string | null | undefined,
  event: AnalyticsEvent,
  props?: Record<string, unknown>,
): Promise<void> {
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key || !distinctId) return;
  try {
    const client = new PostHog(key, {
      host: POSTHOG_CAPTURE_HOST,
      flushAt: 1,
      flushInterval: 0,
    });
    client.capture({ distinctId, event, properties: stripPii(props) });
    await client.shutdown();
  } catch (err) {
    console.warn(`[analytics] server capture ${event} failed:`, err);
  }
}
