import { NextRequest } from 'next/server';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';

/** POST /api/coach/sessions/[id]/game — start a game against the coach. */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToHermes(request, `/api/coach/sessions/${encodeURIComponent(id)}/game`, 'POST');
}
