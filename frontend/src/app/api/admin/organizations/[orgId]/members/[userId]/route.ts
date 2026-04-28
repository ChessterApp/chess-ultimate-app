import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ orgId: string; userId: string }> }
) {
  const { userId: authUserId } = await auth();
  if (!authUserId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { orgId, userId: targetUserId } = await params;

  try {
    const res = await fetch(`${BACKEND_URL}/api/admin/organizations/${orgId}/members/${targetUserId}`, {
      method: 'DELETE',
      headers: { 'X-User-Id': authUserId },
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      return NextResponse.json({ error: 'Backend error' }, { status: res.status });
    }
    return NextResponse.json({ status: 'ok' });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
