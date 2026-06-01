import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ orgId: string }> }
) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { orgId } = await params;

  const incoming = await request.formData();
  const forwarded = new FormData();
  for (const [key, value] of incoming.entries()) {
    forwarded.append(key, value as Blob | string);
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/branding/upload`,
      {
        method: 'POST',
        headers: { 'X-User-Id': userId },
        body: forwarded,
        signal: AbortSignal.timeout(20000),
      }
    );
    const data = await res.json().catch(() => ({ error: 'Backend error' }));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
