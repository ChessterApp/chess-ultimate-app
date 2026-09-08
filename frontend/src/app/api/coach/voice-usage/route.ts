import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/voice-usage — heartbeat proxy for Voice Mode minute metering.
 * Body: { session_id, seconds_delta }. Clerk-authenticated; the user identity is
 * set SERVER-SIDE from the Clerk session — the client-supplied user_id (if any)
 * is never trusted. Forwards to the Hermes internal heartbeat endpoint.
 *
 * Best-effort: metering must never disrupt the live session, so a Hermes failure
 * still returns 200 (the client fires this fire-and-forget with keepalive).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: { session_id?: string; seconds_delta?: number };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const sessionId =
    typeof body.session_id === 'string' && body.session_id
      ? body.session_id
      : '';
  const secondsDelta =
    typeof body.seconds_delta === 'number' && Number.isFinite(body.seconds_delta)
      ? Math.max(0, Math.round(body.seconds_delta))
      : 0;

  if (!sessionId || secondsDelta <= 0) {
    // Nothing to record — accept silently so the client never treats it as an error.
    return NextResponse.json({ ok: true });
  }

  const tier = await resolveUserTier(userId);

  try {
    await fetch(`${HERMES_URL}/internal/voice/heartbeat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({
        user_id: userId, // server-authoritative identity, not from the client
        session_id: sessionId,
        seconds_delta: secondsDelta,
      }),
      signal: AbortSignal.timeout(5000),
    });
  } catch (err) {
    console.warn('[voice-usage] heartbeat forward failed:', err);
    // Fall through — metering is best-effort and must not break the session.
  }

  return NextResponse.json({ ok: true });
}
