import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// Up to three moves played and analysed for ~300 ms each, plus the position before.
const IDEA_TIMEOUT_MS = 6000;

/**
 * POST /api/coach/voice/idea — the student's spoken idea («а если я поставлю
 * ладью на g1?», "what if I take on h4 with the rook?") played on the board and
 * judged by Stockfish, as one "[Idea] …" line the voice hook feeds into Gemini
 * Live before the coach answers — the voice twin of the text coach's block
 * (2026-10-04: the voice coach reasoned about such positions from its head).
 * Body: { text, fen, live_game? }. Returns Hermes' { note, moves, fens }; the
 * client treats any failure as "no line" (an older Hermes answers 404).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: { text?: unknown; fen?: unknown; live_game?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (typeof body.text !== 'string' || !body.text.trim()) {
    return NextResponse.json({ error: 'Missing text' }, { status: 400 });
  }
  if (typeof body.fen !== 'string' || !body.fen.trim()) {
    return NextResponse.json({ error: 'Missing fen' }, { status: 400 });
  }

  const tier = await resolveUserTier(userId);

  try {
    const res = await fetch(`${HERMES_URL}/api/coach/voice/idea`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({ text: body.text, fen: body.fen, live_game: body.live_game === true }),
      signal: AbortSignal.timeout(IDEA_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
