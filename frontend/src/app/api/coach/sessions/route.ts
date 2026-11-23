import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/** The page of the list Hermes is asked for: `limit` and `offset`, digits only (tester 17.11: 1001 sessions). */
function pageQuery(request: NextRequest): string {
  const params = new URLSearchParams();
  for (const key of ['limit', 'offset']) {
    const value = request.nextUrl.searchParams.get(key);
    if (value && /^\d{1,7}$/.test(value)) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : '';
}

/**
 * GET /api/coach/sessions — A page of the current user's coach sessions (`?limit=&offset=`, Hermes' default 30)
 */
export async function GET(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  try {
    const response = await fetch(`${HERMES_URL}/api/coach/sessions${pageQuery(request)}`, {
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

  const denied = await requireApiAccess();
  if (denied) return denied;

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
