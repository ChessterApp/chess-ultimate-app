import { NextRequest, NextResponse } from 'next/server';

// PRD §11.3 #3 — public lookup by token. No auth: the token is the secret.

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params;
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/ownership-transfers/by-token/${encodeURIComponent(token)}`,
      { signal: AbortSignal.timeout(10000) },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Service unavailable' }, { status: 502 });
  }
}
