import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

const FEEDBACK_TIMEOUT_MS = 10000;

/**
 * POST /api/coach/feedback — proxy an explicit 👍/👎 on a coach answer to Hermes.
 * Body: { turn_id, rating (1 | -1 | 0), session_id?, comment?, surface? }.
 * LOG-ONLY signal; the browser never talks to Hermes directly. Clerk-authed.
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: {
    turn_id?: string;
    rating?: number;
    session_id?: string;
    comment?: string;
    surface?: string;
    client_ts?: string;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.turn_id || typeof body.turn_id !== 'string') {
    return NextResponse.json({ error: 'Missing turn_id' }, { status: 400 });
  }
  if (body.rating !== 1 && body.rating !== -1 && body.rating !== 0) {
    return NextResponse.json({ error: 'Invalid rating' }, { status: 400 });
  }

  try {
    const response = await fetch(`${HERMES_URL}/api/coach/feedback`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: JSON.stringify({
        turn_id: body.turn_id,
        rating: body.rating,
        session_id: body.session_id,
        comment: body.comment,
        surface: body.surface ?? 'text',
        client_ts: body.client_ts,
      }),
      signal: AbortSignal.timeout(FEEDBACK_TIMEOUT_MS),
    });

    if (!response.ok) {
      return NextResponse.json({ ok: false }, { status: 502 });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    // Hermes unreachable — the client treats this as a silent failure and
    // reverts its optimistic state; feedback must never interrupt the chat.
    return NextResponse.json({ ok: false }, { status: 502 });
  }
}
