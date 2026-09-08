import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// Some tools run Stockfish or hit external APIs — allow a generous timeout.
const TOOL_TIMEOUT_MS = 90000;

/**
 * POST /api/coach/tool — proxy a single voice-coach tool call to Hermes.
 * Body: { name, args, session_id? }. Clerk-authenticated; the browser never
 * talks to Hermes directly and the user identity is set server-side.
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: { name?: string; args?: Record<string, unknown>; session_id?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.name || typeof body.name !== 'string') {
    return NextResponse.json({ error: 'Missing tool name' }, { status: 400 });
  }

  const tier = await resolveUserTier(userId);

  try {
    const response = await fetch(
      `${HERMES_URL}/api/coach/tool/${encodeURIComponent(body.name)}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId,
          'x-subscription-tier': tier,
        },
        body: JSON.stringify({
          args: body.args ?? {},
          session_id: body.session_id,
        }),
        signal: AbortSignal.timeout(TOOL_TIMEOUT_MS),
      },
    );

    if (!response.ok) {
      // Surface a clear error field the voice hook can read back to the model
      // (so the coach says it's busy instead of the session stalling). Hermes'
      // 429 payload is { detail: { error, message, retry_after, tier } }.
      let payload: unknown = null;
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
      const detail =
        (payload as { detail?: Record<string, unknown> })?.detail ?? payload;
      const d = (detail ?? {}) as Record<string, unknown>;
      const message =
        (typeof d.message === 'string' && d.message) ||
        (typeof d.error === 'string' && d.error) ||
        `Hermes error: ${response.status}`;
      return NextResponse.json(
        {
          error: message,
          rate_limited: response.status === 429,
          retry_after: typeof d.retry_after === 'number' ? d.retry_after : undefined,
        },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
