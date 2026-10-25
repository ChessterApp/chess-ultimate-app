import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: vi.fn(async () => null) }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: vi.fn(async () => 'pro') }));

import { auth } from '@clerk/nextjs/server';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/voice/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/** An SSE body the way Gemini TTS streams it: two audio parts, base64. */
function sseBody(parts: Buffer[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const lines = parts.map((p) => `data: ${JSON.stringify({ candidates: [{ content: { parts: [{ inlineData: { mimeType: 'audio/l16;rate=24000', data: p.toString('base64') } }] } }] })}\n\n`);
  return new ReadableStream({
    start(controller) {
      for (const l of lines) controller.enqueue(enc.encode(l));
      controller.close();
    },
  });
}

/** Raw PCM bytes the way Hermes streams them. */
function rawBody(parts: Buffer[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const p of parts) controller.enqueue(new Uint8Array(p));
      controller.close();
    },
  });
}

const hermesUrl = (u: string) => u.endsWith('/api/coach/voice/tts') && !u.includes('googleapis');
const ENV = ['GEMINI_API_KEY', 'HERMES_URL'] as const;
const saved: Record<string, string | undefined> = {};

describe('POST /api/coach/voice/tts (the voice pipeline, 25.10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const k of ENV) { saved[k] = process.env[k]; delete process.env[k]; }
    (auth as any).mockResolvedValue({ userId: 'user_1' });
  });
  afterEach(() => {
    for (const k of ENV) { if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]; }
    vi.restoreAllMocks();
  });

  it('asks Hermes to read the chunk, with the student id, and passes the PCM through', async () => {
    const a = Buffer.from([1, 0, 2, 0]), b = Buffer.from([3, 0]);
    const fetchMock = vi.fn(async (url: string) => {
      if (!hermesUrl(url)) throw new Error('not hermes');
      return { ok: true, status: 200, body: rawBody([a, b]), headers: new Headers({ 'x-sample-rate': '24000', 'x-tts-model': 'google/gemini-3.8-flash-tts' }), text: async () => '' };
    });
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/octet-stream');
    expect(res.headers.get('X-Sample-Rate')).toBe('24000');
    expect(res.headers.get('X-Tts-Model')).toBe('google/gemini-3.8-flash-tts');
    expect([...Buffer.from(await res.arrayBuffer())]).toEqual([1, 0, 2, 0, 3, 0]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('http://localhost:8642/api/coach/voice/tts');
    expect((init.headers as Record<string, string>)['X-User-Id']).toBe('user_1');
    expect(JSON.parse(init.body as string)).toEqual({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' });
  });

  it('an older Hermes (404) or an unreachable one: straight to Google, the key on the server', async () => {
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    const a = Buffer.from([1, 0, 2, 0]), b = Buffer.from([3, 0]);
    const fetchMock = vi.fn(async (url: string) => {
      if (hermesUrl(url)) return { ok: false, status: 404, body: null, headers: new Headers(), text: async () => 'Not Found' };
      return { ok: true, status: 200, body: sseBody([a, b]), headers: new Headers(), text: async () => '' };
    });
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' }));
    expect(res.status).toBe(200);
    expect([...Buffer.from(await res.arrayBuffer())]).toEqual([1, 0, 2, 0, 3, 0]);
    const google = fetchMock.mock.calls.find(([u]) => String(u).includes('googleapis')) as unknown as [string, RequestInit];
    expect(google[0]).toContain('gemini-3.8-flash-tts:streamGenerateContent?alt=sse');
    expect((google[1].headers as Record<string, string>)['x-goog-api-key']).toBe('AQ.test-key');
    // unreachable Hermes: the same fallback
    global.fetch = vi.fn(async (url: string) => {
      if (hermesUrl(url)) throw new Error('ECONNREFUSED');
      return { ok: true, status: 200, body: sseBody([a]), headers: new Headers(), text: async () => '' };
    }) as any;
    expect((await POST(makeRequest({ text: 'Привет' }))).status).toBe(200);
  });

  it('refuses without a user, without text, without any way to read; a quota, no credit and a failure are told apart', async () => {
    const { POST } = await import('../voice/tts/route');
    (auth as any).mockResolvedValue({ userId: null });
    expect((await POST(makeRequest({ text: 'x' }))).status).toBe(401);
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    expect((await POST(makeRequest({}))).status).toBe(400);
    global.fetch = vi.fn(async () => ({ ok: false, status: 404, body: null, headers: new Headers(), text: async () => '' })) as any;
    expect((await POST(makeRequest({ text: 'x' }))).status).toBe(500);   // no Hermes route, no Google key
    const upstream = (status: number) => vi.fn(async () => ({ ok: false, status, body: null, headers: new Headers({ 'retry-after': '7' }), text: async () => 'no' })) as any;
    global.fetch = upstream(429);
    const quota = await POST(makeRequest({ text: 'Привет' }));
    expect(quota.status).toBe(429);
    expect(quota.headers.get('Retry-After')).toBe('7');
    global.fetch = upstream(402);
    expect((await POST(makeRequest({ text: 'Привет' }))).status).toBe(402);
    global.fetch = upstream(500);
    expect((await POST(makeRequest({ text: 'Привет' }))).status).toBe(502);
  });
});
