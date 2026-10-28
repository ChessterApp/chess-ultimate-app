import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';
import { requestLocale } from '@/i18n/detect';
import { hermesErrorFrame, unreachableFrame, type CoachErrorFrame } from '@/lib/coach/coach-errors';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';
const ACTIONS = new Set(['move', 'resign', 'takeback', 'continue', 'comment']);  // continue: the game goes on from an earlier ply (26.10)

/**
 * POST /api/coach/sessions/[id]/game/[boardId]/(move|resign|takeback|continue|comment)
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
  // Cookie → Accept-Language, as the page picks its language (seam audit 28.10).
  const locale = requestLocale(request);
  // One SSE error frame, never a thrown handler: a timeout used to become Next's 500 and «HTTP 500» in the chat,
  // and Hermes's own reason was replaced by «Hermes error: 404» (seam audit 28.10).
  const errorStream = (frame: CoachErrorFrame) =>
    new Response(`data: ${JSON.stringify(frame)}\n\n`, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  let hermesResponse: Response;
  try {
    hermesResponse = await fetch(`${HERMES_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
      body: JSON.stringify({ locale, ...(body as Record<string, unknown>) }),
      signal: AbortSignal.timeout(30000),
    });
  } catch (err: unknown) {
    return errorStream(unreachableFrame(err));
  }
  if (!hermesResponse.ok) return errorStream(await hermesErrorFrame(hermesResponse));
  if (!hermesResponse.body) return errorStream({ error: 'empty answer', error_code: 'server' });
  return new Response(hermesResponse.body, {
    headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' },
  });
}
