import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

/**
 * POST /api/review {pgn, source?} → proxies to Flask, returns {review_id, status}.
 * Signed-in callers' Clerk id rides along as `analytics_user_id` so Flask can
 * capture `game_review_completed` (it does NOT enable insight persistence).
 */
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  if (!body?.pgn || typeof body.pgn !== 'string') {
    return NextResponse.json({ error: 'pgn is required' }, { status: 400 });
  }
  const { userId } = await auth();
  try {
    const res = await fetch(`${BACKEND_URL}/api/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pgn: body.pgn,
        ...(userId ? { analytics_user_id: userId } : {}),
        ...(typeof body.source === 'string' ? { source: body.source } : {}),
      }),
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Review service unavailable' }, { status: 502 });
  }
}
