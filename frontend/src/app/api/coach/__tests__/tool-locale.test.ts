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
});
