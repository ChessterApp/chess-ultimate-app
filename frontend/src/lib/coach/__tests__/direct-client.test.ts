import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { directPost, resetDirectForTests } from '../direct-client';

const PASS = { url: 'https://coach-api.chesster.io', token: 'v1.a.b', expiresAt: Date.now() + 300_000 };

function mockFetch(direct: (init?: RequestInit) => Response | Promise<Response>, pass: unknown = { direct: PASS }) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === '/api/coach/direct-pass') return Response.json(pass);
    if (url.startsWith(PASS.url)) return direct(init);
    throw new Error(`unexpected ${url}`);
  });
  vi.stubGlobal('fetch', fn);
  return calls;
}

describe('the direct path from the page (23.11)', () => {
  beforeEach(() => resetDirectForTests());
  afterEach(() => vi.unstubAllGlobals());

  it('sends the request straight to the coach server with the pass, without the site cookies', async () => {
    const calls = mockFetch(() => new Response('data: {}\n\n', { status: 200 }));
    const res = await directPost('chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    expect(res?.status).toBe(200);
    const sent = calls.find((c) => c.url === `${PASS.url}/direct/chat`)!;
    expect(new Headers(sent.init?.headers).get('Authorization')).toBe(`Bearer ${PASS.token}`);
    expect(sent.init?.credentials).toBe('omit');
    // The pass is reused, not asked again for the next request.
    await directPost('voice/stt', { method: 'POST', body: 'x' });
    expect(calls.filter((c) => c.url === '/api/coach/direct-pass')).toHaveLength(1);
  });

  it('is off when the site has no direct path, and never asks again', async () => {
    const calls = mockFetch(() => new Response('', { status: 200 }), { direct: null });
    expect(await directPost('chat', { method: 'POST' })).toBeNull();
    expect(await directPost('chat', { method: 'POST' })).toBeNull();
    expect(calls.filter((c) => c.url === '/api/coach/direct-pass')).toHaveLength(1);
  });

  it('a network failure goes through the site, and the path rests', async () => {
    const calls = mockFetch(() => { throw new TypeError('Failed to fetch'); });
    expect(await directPost('voice/stt', { method: 'POST', body: 'x' })).toBeNull();
    expect(await directPost('voice/stt', { method: 'POST', body: 'x' })).toBeNull();
    expect(calls.filter((c) => c.url.startsWith(PASS.url))).toHaveLength(1);
  });

  it('a refused pass is renewed next time; a limit is told by the site without resting the path', async () => {
    let status = 401;
    const calls = mockFetch(() => new Response('{}', { status }));
    expect(await directPost('chat', { method: 'POST' })).toBeNull();
    status = 429;
    expect(await directPost('chat', { method: 'POST' })).toBeNull();
    expect(calls.filter((c) => c.url === '/api/coach/direct-pass')).toHaveLength(2);
    status = 200;
    expect((await directPost('chat', { method: 'POST' }))?.status).toBe(200);
  });

  it("the student's stop stops the direct request", async () => {
    mockFetch((init) => new Promise((_, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))));
    const stop = new AbortController();
    const pending = directPost('chat', { method: 'POST', signal: stop.signal });
    await new Promise((r) => setTimeout(r, 0));
    stop.abort();
    await expect(pending).rejects.toThrow(/Abort/);
  });
});
