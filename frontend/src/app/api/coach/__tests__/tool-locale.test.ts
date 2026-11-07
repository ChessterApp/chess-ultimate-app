import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'user_t' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'free' }));

import { NextRequest } from 'next/server';
import { POST } from '../tool/route';

// Seam audit 28.10: voice get_puzzle / get_topic calls reached Hermes without a language, so a Kazakh
// interface got Russian lesson and topic texts.
describe('POST /api/coach/tool — interface language', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue(new Response(JSON.stringify({ result: {} }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('forwards the locale the page resolves (cookie → Accept-Language)', async () => {
    const request = new NextRequest('http://localhost/api/coach/tool', {
      method: 'POST',
      body: JSON.stringify({ name: 'get_puzzle', args: { theme: 'pin' } }),
      headers: { 'accept-language': 'kk-KZ,ru;q=0.5' },
    });
    await POST(request);
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(sent.locale).toBe('kz');
    expect(sent.args).toEqual({ theme: 'pin' });
  });

  it('forwards the position the board shows, for the arrows (06.11)', async () => {
    const fen = 'r1bqkb1r/pppp1ppp/2n2n2/4N3/4P3/8/PPPP1PPP/RNBQKB1R b KQkq - 0 4';
    const request = new NextRequest('http://localhost/api/coach/tool', {
      method: 'POST',
      body: JSON.stringify({ name: 'board_control', args: {}, shown_fen: fen }),
    });
    await POST(request);
    const sent = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(sent.shown_fen).toBe(fen);
  });
});
