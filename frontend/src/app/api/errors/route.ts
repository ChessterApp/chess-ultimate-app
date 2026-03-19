import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const errors = body?.errors;
    if (!Array.isArray(errors) || errors.length === 0) {
      return NextResponse.json({ error: 'No errors provided' }, { status: 400 });
    }
    // Log to server stdout (picked up by PM2 logs)
    for (const err of errors.slice(0, 20)) {
      console.error('[CLIENT_ERROR]', JSON.stringify({
        type: err.type,
        message: err.message?.substring(0, 500),
        url: err.url,
        timestamp: err.timestamp,
      }));
    }
    return NextResponse.json({ received: errors.length });
  } catch {
    return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
  }
}
