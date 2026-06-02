import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// PRD §11.2 #7 — bulk-invite proxy (Phase 2).
//
// Forwards POST to backend POST /api/admin/organizations/<id>/invites/bulk
// with the caller's Clerk user id pinned to X-User-Id, matching the
// existing single-invite proxy's auth shape.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { orgId } = await params;
  const body = await request.json();

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/invites/bulk`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
