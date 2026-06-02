import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// PRD §11.2 #4 — branded sender domain proxy.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

async function pinned(orgId: string, method: 'GET' | 'POST' | 'DELETE', body?: unknown) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const init: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
    },
    signal: AbortSignal.timeout(10000),
  };
  if (body !== undefined) init.body = JSON.stringify(body);
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/email-sender`,
      init,
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  return pinned(orgId, 'GET');
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  const body = await req.json().catch(() => ({}));
  return pinned(orgId, 'POST', body);
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { orgId } = await params;
  return pinned(orgId, 'DELETE');
}
