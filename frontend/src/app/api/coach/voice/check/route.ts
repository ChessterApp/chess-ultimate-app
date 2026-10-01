import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';
const CHECK_TIMEOUT_MS = 4000;

/**
 * POST /api/coach/voice/check — a sentence the voice coach just said, checked
 * on the board by Hermes (the same check the text coach's answers pass before
 * they are shown). Body: { text, fen?, pgn?, question? }. Returns Hermes'
 * { issues: string[] }; any failure is "no issues" (an older Hermes answers 404).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: { text?: unknown; fen?: unknown; pgn?: unknown; question?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (typeof body.text !== 'string' || !body.text.trim()) {
    return NextResponse.json({ error: 'Missing text' }, { status: 400 });
  }

  const tier = await resolveUserTier(userId);

  try {
    const res = await fetch(`${HERMES_URL}/api/coach/voice/check`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({
        text: body.text,
        fen: typeof body.fen === 'string' ? body.fen : undefined,
        pgn: typeof body.pgn === 'string' ? body.pgn : undefined,
        question: typeof body.question === 'string' ? body.question : undefined,
      }),
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
