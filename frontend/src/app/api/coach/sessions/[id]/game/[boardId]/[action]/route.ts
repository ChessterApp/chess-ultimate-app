import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';
const ACTIONS = new Set(['move', 'resign', 'takeback', 'comment']);

/**
 * POST /api/coach/sessions/[id]/game/[boardId]/(move|resign|takeback|comment)
 * move / resign / takeback answer JSON (Hermes' game payload, or its error
 * `detail` with the same status). comment streams SSE straight through.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string; boardId: string; action: string }> },
) {
  const { id, boardId, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: 'Unknown action' }, { status: 404 });
  }
  const path = `/api/coach/sessions/${encodeURIComponent(id)}/game/${encodeURIComponent(boardId)}/${action}`;
  if (action !== 'comment') {
    return proxyToHermes(request, path, 'POST');
  }

  const { userId } = await auth();
  if (!userId) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const locale = request.cookies.get('NEXT_LOCALE')?.value || 'ru';
  const hermesResponse = await fetch(`${HERMES_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
    body: JSON.stringify({ locale, ...(body as Record<string, unknown>) }),
    signal: AbortSignal.timeout(30000),
  });
  if (!hermesResponse.ok || !hermesResponse.body) {
    return new Response(`data: ${JSON.stringify({ error: `Hermes error: ${hermesResponse.status}` })}\n\n`, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }
  return new Response(hermesResponse.body, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
  });
}
