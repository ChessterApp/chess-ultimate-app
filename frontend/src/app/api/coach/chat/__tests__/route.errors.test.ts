import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next/server', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/server')>()),
  after: () => {},
}));
vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'user_e' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'free' }));
vi.mock('@/lib/analytics/server', () => ({ captureServer: () => {} }));

import { NextRequest } from 'next/server';
import { POST } from '../route';

// Seam audit 28.10: Hermes's 429 became «Hermes error: 429» in the chat bubble; the locale ignored Accept-Language.
function req(body: unknown, headers: Record<string, string> = {}) {
  return new NextRequest('http://localhost/api/coach/chat', {
    method: 'POST',
    body: JSON.stringify(body),
    headers,
  });
}

function frames(text: string) {
  return text
    .split('\n')
    .filter((l) => l.startsWith('data: '))
    .map((l) => JSON.parse(l.slice(6)));
}

describe('POST /api/coach/chat — errors and language', () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("turns Hermes's 429 into a rate-limit frame with the wait", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { error: 'rate_limit_exceeded', message: 'Rate limit exceeded for free tier. Limit: 30 requests per minute.', retry_after: 17, tier: 'free' } }),
        { status: 429, headers: { 'content-type': 'application/json' } },
      ),
    );
    const res = await POST(req({ message: 'hi' }));
    const [frame] = frames(await res.text());
    expect(frame.error_code).toBe('rate_limited');
    expect(frame.rate_limited).toBe(true);
    expect(frame.retry_after).toBe(17);
    expect(frame.error).not.toBe('Hermes error: 429');
  });

  it('a Hermes that cannot be reached gives an unreachable frame', async () => {
    fetchMock.mockRejectedValue(new TypeError('fetch failed'));
    const res = await POST(req({ message: 'hi' }));
    expect(frames(await res.text())[0]).toMatchObject({ error_code: 'unreachable' });
  });

  async function sentLocale(headers: Record<string, string>) {
    fetchMock.mockResolvedValue(new Response('{}', { status: 500 }));
    const res = await POST(req({ message: 'e4' }, headers));
    await res.text();
    return JSON.parse(fetchMock.mock.calls[0][1].body as string).locale;
  }

  it('takes the language as the page does: cookie, then Accept-Language', async () => {
    expect(await sentLocale({ 'accept-language': 'kk-KZ,kk;q=0.9' })).toBe('kz');
    fetchMock.mockClear();
    expect(await sentLocale({ cookie: 'NEXT_LOCALE=en', 'accept-language': 'kk-KZ' })).toBe('en');
    fetchMock.mockClear();
    expect(await sentLocale({ cookie: 'NEXT_LOCALE=xx', 'accept-language': 'kk' })).toBe('kz');
    fetchMock.mockClear();
    expect(await sentLocale({})).toBe('ru');
  });
});
