import { NextRequest, NextResponse } from 'next/server';
import { auth, currentUser } from '@clerk/nextjs/server';

// PRD §7 — self-serve school deletion request proxy.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

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

  let requesterEmail: string | undefined;
  try {
    const user = await currentUser();
    requesterEmail = user?.emailAddresses?.[0]?.emailAddress;
  } catch {
    requesterEmail = undefined;
  }

  try {
    const res = await fetch(
      `${BACKEND_URL}/api/admin/organizations/${orgId}/delete-request`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Id': userId,
        },
        body: JSON.stringify({ ...body, requester_email: requesterEmail }),
        signal: AbortSignal.timeout(10000),
      },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
