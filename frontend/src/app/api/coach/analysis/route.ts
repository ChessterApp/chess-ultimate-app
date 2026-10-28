import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';
import { resolveUserTier } from '@/lib/subscription-tier';
import { contextNoteOf } from '@/lib/coach/click-analysis';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/analysis — non-streaming analysis proxy to Hermes.
 * Mirrors the Flask /api/chat/analysis contract. The browser never talks to
 * Hermes directly; the Clerk user id is forwarded as X-User-Id.
 * Passes Hermes' JSON response and status straight through (including 429).
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  let body: {
    fen?: string;
    query?: string;
    conversation_id?: string;
    context_type?: string;
    context_note?: string;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.fen || typeof body.fen !== 'string') {
    return NextResponse.json({ error: 'Missing fen' }, { status: 400 });
  }
  if (!body.query || typeof body.query !== 'string') {
    return NextResponse.json({ error: 'Missing query' }, { status: 400 });
  }

  // Same tier the coach proxies send; without it Hermes rate-limits every
  // analysis as free (28.10).
  const tier = await resolveUserTier(userId);

  try {
    const response = await fetch(`${HERMES_URL}/api/coach/analysis`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({
        fen: body.fen,
        query: body.query,
        conversation_id: body.conversation_id,
        context_type: body.context_type,
        // Master stats / engine lines of a click-analysis: apart from the
        // query, which Hermes caps at 2000 characters (28.10).
        context_note: contextNoteOf(body.context_note),
      }),
      signal: AbortSignal.timeout(60000),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
