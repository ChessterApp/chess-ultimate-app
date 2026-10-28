import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'user_g' }) }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));

import { NextRequest } from 'next/server';
import { POST } from '../[id]/game/[boardId]/[action]/route';

// Seam audit 28.10: the comment proxy threw (Next 500 → «HTTP 500» in the chat) when Hermes was unreachable,
// passed «Hermes error: 404» as the coach's words, and took the language from the cookie only.
function call(headers: Record<string, string> = {}) {
  const request = new NextRequest('http://localhost/api/coach/sessions/s1/game/g1/comment', {
    method: 'POST',
    body: JSON.stringify({ event: 'move' }),
    headers,
  });
  return POST(request, { params: Promise.resolve({ id: 's1', boardId: 'g1', action: 'comment' }) });
}

function frames(text: string) {
  return text
    .split('\n')
    .filter((l) => l.startsWith('data: '))
    .map((l) => JSON.parse(l.slice(6)));
}

describe('POST .../game/[boardId]/comment', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('answers an SSE error frame, not a 500, when Hermes cannot be reached', async () => {
    fetchMock.mockRejectedValue(new DOMException('The operation was aborted due to timeout', 'TimeoutError'));
    const res = await call();
    expect(res.status).toBe(200);
    expect(frames(await res.text())[0]).toMatchObject({ error_code: 'unreachable' });
  });

  it("keeps Hermes's reason for a failed comment", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Game not found' }), { status: 404 }));
    const res = await call();
    const [frame] = frames(await res.text());
    expect(frame.error_code).toBe('not_found');
    expect(frame.error).toBe('Game not found');
  });

  it('sends the language the page shows (Accept-Language without a cookie)', async () => {
    fetchMock.mockResolvedValue(new Response('data: {"done": true}\n\n', { status: 200 }));
    await (await call({ 'accept-language': 'kk-KZ' })).text();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).locale).toBe('kz');
  });
});
