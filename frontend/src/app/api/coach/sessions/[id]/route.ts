import { NextRequest } from 'next/server';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';

type Ctx = { params: Promise<{ id: string }> };

/** PATCH /api/coach/sessions/[id] — rename a session or switch its active board. */
export async function PATCH(request: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return proxyToHermes(request, `/api/coach/sessions/${encodeURIComponent(id)}`, 'PATCH');
}

/** DELETE /api/coach/sessions/[id] — delete a session and its boards/messages. */
export async function DELETE(_request: NextRequest, { params }: Ctx) {
  const { id } = await params;
  return proxyToHermes(null, `/api/coach/sessions/${encodeURIComponent(id)}`, 'DELETE');
}
