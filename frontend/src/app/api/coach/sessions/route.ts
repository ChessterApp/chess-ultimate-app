import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * GET /api/coach/sessions — List coach sessions for the current user
 */
export async function GET() {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const response = await fetch(`${HERMES_URL}/api/coach/sessions`, {
      headers: { 'X-User-Id': userId },
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Hermes error: ${response.status}` },
        { status: response.status }
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
 * POST /api/coach/sessions — Create a new coach session
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: { title?: string } = {};
  try {
    body = await request.json();
  } catch {
    // Empty body is fine, title is optional
  }

  try {
    const response = await fetch(`${HERMES_URL}/api/coach/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: JSON.stringify({ title: body.title }),
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Hermes error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 201 });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
