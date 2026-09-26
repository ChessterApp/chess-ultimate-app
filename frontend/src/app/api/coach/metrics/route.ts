import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/metrics — thin proxy for voice-coach latency telemetry.
 * Best-effort: forwards the record to Hermes and never surfaces a failure to
 * the caller. The client fires these fire-and-forget off the audio hot path,
 * so a 404 (while the Hermes endpoint is being built) or any error is fine.
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  try {
    await fetch(`${HERMES_URL}/api/coach/metrics`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(2000),
    });
  } catch {
    // Telemetry must never surface an error — swallow and move on.
  }

  return NextResponse.json({ ok: true });
}
