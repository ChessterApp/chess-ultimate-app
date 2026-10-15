import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// Word rules and a look at the session: no engine, no model.
const INTENT_TIMEOUT_MS = 2500;

/**
 * POST /api/coach/voice/intent — what the student's words ask for (a game command, a move in the game,
 * a puzzle, a review, a famous game, an opening, a concept, a question about their own board), decided
 * by Hermes (src/intent.py) for the voice hook, which kept its own drifting copies of these rules
 * (inventory 2026-10-15). Body: { text, session_id?, fen?, pgn? }. Returns Hermes' { kind, … }; the
 * hook treats any failure as "ask nothing" and falls back to its own gates (an older Hermes answers 404).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: { text?: unknown; session_id?: unknown; fen?: unknown; pgn?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (typeof body.text !== 'string' || !body.text.trim()) {
    return NextResponse.json({ error: 'Missing text' }, { status: 400 });
  }
  const str = (v: unknown, max: number) => (typeof v === 'string' && v.trim() ? v.slice(0, max) : undefined);

  const tier = await resolveUserTier(userId);

  try {
    const res = await fetch(`${HERMES_URL}/api/coach/voice/intent`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({
        text: body.text.slice(0, 600),
        session_id: str(body.session_id, 100),
        fen: str(body.fen, 120),
        pgn: str(body.pgn, 20000),
      }),
      signal: AbortSignal.timeout(INTENT_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
