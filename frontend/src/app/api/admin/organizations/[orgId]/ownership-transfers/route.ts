import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// PRD §11.3 #3 — owner-facing transfer list + create.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

async function proxy(
  req: NextRequest,
  orgId: string,
  userId: string,
  method: 'GET' | 'POST',
  body?: Record<string, unknown>,
) {
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/ownership-transfers`,
      {
        method,
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId,
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout(10000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { orgId } = await params;
  return proxy(req, orgId, userId, 'GET');
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { orgId } = await params;
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  return proxy(req, orgId, userId, 'POST', body);
}
