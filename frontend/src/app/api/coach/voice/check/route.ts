import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';
const CHECK_TIMEOUT_MS = 4000;
// Same bound as /api/coach/voice/intent: the hook now sends the loaded game's pgn here (28.10).
const PGN_MAX = 20000;
// The coach's earlier sentences of the answer, for «больше ничего не висит» (30.10).
const PREVIOUS_MAX = 1500;

/**
 * POST /api/coach/voice/check — a sentence the voice coach just said, checked
 * on the board by Hermes (the same check the text coach's answers pass before
 * they are shown). Body: { text, fen?, pgn?, question?, session_id?, previous?, engine? }. Returns Hermes'
 * { issues: string[], engine?: boolean } (engine: whether the engine or the tablebase was asked; engine=false in
 * the body asks for the board check alone); any failure is "no issues" (an older Hermes answers 404).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: { text?: unknown; fen?: unknown; pgn?: unknown; question?: unknown; session_id?: unknown; previous?: unknown; engine?: unknown };
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
        pgn: typeof body.pgn === 'string' && body.pgn.trim() ? body.pgn.slice(0, PGN_MAX) : undefined,
        question: typeof body.question === 'string' ? body.question : undefined,
        session_id: typeof body.session_id === 'string' ? body.session_id : undefined,
        previous: typeof body.previous === 'string' && body.previous.trim() ? body.previous.slice(-PREVIOUS_MAX) : undefined,
        engine: typeof body.engine === 'boolean' ? body.engine : undefined,
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
