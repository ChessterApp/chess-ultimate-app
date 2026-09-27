import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * GET /api/coach/history/[id] — conversation history proxy to Hermes.
 * Mirrors the Flask /api/chat/history/<id> contract. Passes Hermes'
 * {success, conversation, messages} response and status straight through
 * (404 on a non-owned or missing conversation).
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  const { id } = await params;

  try {
    const response = await fetch(
      `${HERMES_URL}/api/coach/history/${encodeURIComponent(id)}`,
      {
        headers: { 'X-User-Id': userId },
        signal: AbortSignal.timeout(10000),
      },
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
