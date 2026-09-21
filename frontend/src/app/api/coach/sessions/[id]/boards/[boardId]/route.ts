import { NextRequest } from 'next/server';
import { proxyToHermes } from '@/lib/coach/hermes-proxy';

type Ctx = { params: Promise<{ id: string; boardId: string }> };

const path = (id: string, boardId: string) =>
  `/api/coach/sessions/${encodeURIComponent(id)}/boards/${encodeURIComponent(boardId)}`;

/** PATCH — position / ply / orientation / title / active. */
export async function PATCH(request: NextRequest, { params }: Ctx) {
  const { id, boardId } = await params;
  return proxyToHermes(request, path(id, boardId), 'PATCH');
}

/** DELETE — close a board. */
export async function DELETE(_request: NextRequest, { params }: Ctx) {
  const { id, boardId } = await params;
  return proxyToHermes(null, path(id, boardId), 'DELETE');
}
