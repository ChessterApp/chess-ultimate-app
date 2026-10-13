import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next/server', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/server')>()),
  after: () => {},
}));
vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'user_f' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'free' }));
vi.mock('@/lib/analytics/server', () => ({ captureServer: () => {} }));

import { NextRequest } from 'next/server';
import { POST } from '../route';

function req(body: unknown) {
  return new NextRequest('http://localhost/api/coach/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/coach/chat — upstream body', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue(new Response('{}', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  async function upstreamBody(body: unknown) {
    const res = await POST(req(body));
    await res.text();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    return JSON.parse(fetchMock.mock.calls[0][1].body as string);
  }

  it('forwards board_id with the client fields Hermes accepts', async () => {
    const sent = await upstreamBody({
      message: 'best move?',
      fen: '8/8/8/8/8/8/8/8 w - - 0 1',
      session_id: 's1',
      context_note: '[Review context]',
      board_id: 'board-2',
    });
    expect(sent).toMatchObject({
      message: 'best move?',
      fen: '8/8/8/8/8/8/8/8 w - - 0 1',
      session_id: 's1',
      context_note: '[Review context]',
      board_id: 'board-2',
    });
  });

  it('omits board_id when the client sends none', async () => {
    const sent = await upstreamBody({ message: 'hi' });
    expect(sent).not.toHaveProperty('board_id');
  });
});
