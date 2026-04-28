import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ orgId: string }> }
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { orgId } = await params;
  const url = new URL(request.url);
  const userIdFilter = url.searchParams.get('user_id');

  try {
    const backendUrl = `${BACKEND_URL}/api/admin/organizations/${orgId}/members${userIdFilter ? `?user_id=${userIdFilter}` : ''}`;
    const res = await fetch(backendUrl, {
      headers: { 'X-User-Id': userId },
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      return NextResponse.json({ error: 'Backend error' }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
