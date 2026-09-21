import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * Forward a Clerk-authenticated request to a Hermes endpoint, stamping the
 * user id server-side. Shared by the session/board management proxies so each
 * route file is one line per method instead of a copy of the same handler.
 */
export async function proxyToHermes(
  request: NextRequest | null,
  path: string,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  opts: { body?: unknown; okStatus?: number } = {},
): Promise<NextResponse> {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let body: unknown = opts.body;
  if (body === undefined && request && method !== 'GET' && method !== 'DELETE') {
    try {
      body = await request.json();
    } catch {
      body = {};
    }
  }

  try {
    const response = await fetch(`${HERMES_URL}${path}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });

    if (!response.ok) {
      let detail: unknown;
      try {
        detail = await response.json();
      } catch {
        detail = undefined;
      }
      return NextResponse.json(
        { error: `Hermes error: ${response.status}`, detail },
        { status: response.status },
      );
    }
    const data = await response.json();
    return NextResponse.json(data, { status: opts.okStatus ?? 200 });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
