import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * GET /api/coach/sessions/[id]/messages — proxy a session's message history
 * from Hermes. Clerk-authenticated; the browser never talks to Hermes directly.
 * Optional ?limit=N forwards through to return the last N messages.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = await params;
  const limit = request.nextUrl.searchParams.get('limit');
  const query = limit ? `?limit=${encodeURIComponent(limit)}` : '';

  try {
    const response = await fetch(
      `${HERMES_URL}/api/coach/sessions/${encodeURIComponent(id)}/messages${query}`,
      {
        headers: { 'X-User-Id': userId },
        signal: AbortSignal.timeout(10000),
      },
    );

    if (!response.ok) {
      return NextResponse.json(
        { error: `Hermes error: ${response.status}` },
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

/**
 * POST /api/coach/sessions/[id]/messages — append a message to a Hermes session
 * without running an agent turn (used for voice transcript write-back).
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { id } = await params;

  let body: {
    role?: string;
    content?: string;
    source?: string;
    client_ts?: string;
    turn_id?: string;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!body.role || !body.content || typeof body.content !== 'string') {
    return NextResponse.json(
      { error: 'Missing role or content' },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(
      `${HERMES_URL}/api/coach/sessions/${encodeURIComponent(id)}/messages`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId,
        },
        body: JSON.stringify({
          role: body.role,
          content: body.content,
          source: body.source,
          // Phase 2: true utterance time + turn correlation id (voice write-back).
          client_ts: typeof body.client_ts === 'string' ? body.client_ts : undefined,
          turn_id: typeof body.turn_id === 'string' ? body.turn_id : undefined,
        }),
        signal: AbortSignal.timeout(10000),
      },
    );

    if (!response.ok) {
      return NextResponse.json(
        { error: `Hermes error: ${response.status}` },
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
