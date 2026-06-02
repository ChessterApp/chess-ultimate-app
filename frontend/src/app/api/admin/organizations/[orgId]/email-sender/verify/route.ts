import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ orgId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { orgId } = await params;
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/email-sender/verify`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-User-Id': userId },
        signal: AbortSignal.timeout(10000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
