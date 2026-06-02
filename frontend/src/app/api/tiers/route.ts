import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';

export const revalidate = 300; // cache for 5 min

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/tiers`, {
      signal: AbortSignal.timeout(5000),
      next: { revalidate: 300 },
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
