import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// PRD §11.3 #3 — owner revokes a pending or accepted transfer.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ orgId: string; transferId: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  const { orgId, transferId } = await params;
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/ownership-transfers/${transferId}/revoke`,
      {
        method: 'POST',
        headers: { 'X-User-Id': userId },
        signal: AbortSignal.timeout(10000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
