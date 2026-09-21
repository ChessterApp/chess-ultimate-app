import { NextRequest } from 'next/server';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';

type Ctx = { params: Promise<{ id: string }> };

/** GET /api/coach/sessions/[id]/boards — the session's boards (tabs) and the active one. */
export async function GET(_request: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return proxyToHermes(null, `/api/coach/sessions/${encodeURIComponent(id)}/boards`, 'GET');
}

/** POST /api/coach/sessions/[id]/boards — open a board (study / puzzle / game / master_game). */
export async function POST(request: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return proxyToHermes(request, `/api/coach/sessions/${encodeURIComponent(id)}/boards`, 'POST', {
    okStatus: 201,
  });
}
