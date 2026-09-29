import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// Depth-16 analysis of a fresh position takes 1–2 s on the coach host.
const ENGINE_NOTE_TIMEOUT_MS = 8000;

/**
 * POST /api/coach/voice/engine-note — Stockfish's top moves for a board
 * position, as one "[Engine] …" line the voice hook feeds into Gemini Live so
 * questions about the current position need no tool round trip. The text coach
 * page calls it too, whenever the position changes: the analysis lands in
 * Hermes' cache and the next question about the position starts from it.
 * Body: { fen }. Returns Hermes' { fen, note, best, lines } or an error status;
 * the client treats any failure as "no note" (older Hermes answers 404).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: { fen?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (typeof body.fen !== 'string' || !body.fen.trim()) {
    return NextResponse.json({ error: 'Missing fen' }, { status: 400 });
  }

  const tier = await resolveUserTier(userId);

  try {
    const res = await fetch(`${HERMES_URL}/api/coach/voice/engine-note`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({ fen: body.fen }),
      signal: AbortSignal.timeout(ENGINE_NOTE_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
