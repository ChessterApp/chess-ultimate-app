import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export async function GET(req: NextRequest) {
  const slug = req.nextUrl.searchParams.get('slug') ?? '';
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/subdomains/check?slug=${encodeURIComponent(slug)}`,
      { signal: AbortSignal.timeout(5000) },
    );
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { available: false, reason: 'service_unavailable' },
      { status: 502 },
    );
  }
}
