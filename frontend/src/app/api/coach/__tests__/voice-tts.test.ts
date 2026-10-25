import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: vi.fn(async () => null) }));

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

/** Raw PCM bytes the way OpenRouter's speech endpoint answers. */
function rawBody(parts: Buffer[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const p of parts) controller.enqueue(new Uint8Array(p));
      controller.close();
    },
  });
}

const ENV = ['GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'COACH_TTS_MODEL', 'COACH_TTS_VOICE', 'COACH_TTS_MODEL_KK', 'COACH_TTS_VOICE_KK'] as const;
const saved: Record<string, string | undefined> = {};

describe('POST /api/coach/voice/tts (the voice pipeline, 25.10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    for (const k of ENV) { saved[k] = process.env[k]; delete process.env[k]; }
  });
  afterEach(() => {
    for (const k of ENV) { if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]; }
    vi.restoreAllMocks();
  });

  it('reads a chunk through OpenRouter when its key is set: ElevenLabs Flash for Russian, raw PCM passed through', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    process.env.OPENROUTER_API_KEY = 'sk-or-test';
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    const a = Buffer.from([1, 0, 2, 0]), b = Buffer.from([3, 0]);
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, body: rawBody([a, b]), headers: new Headers({ 'content-type': 'audio/pcm;rate=24000;channels=1' }), text: async () => '' }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/octet-stream');
    expect(res.headers.get('X-Sample-Rate')).toBe('24000');
    expect(res.headers.get('X-Tts-Model')).toBe('elevenlabs/eleven-flash-v2.5');
    expect([...Buffer.from(await res.arrayBuffer())]).toEqual([1, 0, 2, 0, 3, 0]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('https://openrouter.ai/api/v1/audio/speech');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer sk-or-test');
    expect(JSON.parse(init.body as string)).toEqual({ model: 'elevenlabs/eleven-flash-v2.5', input: 'Сейчас посмотрю на позицию.', voice: '21m00Tcm4TlvDq8ikWAM', response_format: 'pcm' });
  });

  it('reads Kazakh through Gemini on OpenRouter, the model heard reading it well', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    process.env.OPENROUTER_API_KEY = 'sk-or-test';
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, body: rawBody([Buffer.from([1, 0])]), headers: new Headers({ 'content-type': 'audio/pcm;rate=24000;channels=1' }), text: async () => '' }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Жақсы жүріс!', locale: 'kk' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('X-Tts-Model')).toBe('google/gemini-3.8-flash-tts');
    expect(JSON.parse((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body as string)).toMatchObject({ model: 'google/gemini-3.8-flash-tts', voice: 'Kore' });
  });

  it('goes straight to Google without an OpenRouter key: the SSE frames become bytes, the key stays on the server', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    const a = Buffer.from([1, 0, 2, 0]), b = Buffer.from([3, 0]);
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, body: sseBody([a, b]), headers: new Headers(), text: async () => '' }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('X-Sample-Rate')).toBe('24000');
    expect([...Buffer.from(await res.arrayBuffer())]).toEqual([1, 0, 2, 0, 3, 0]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain('gemini-3.8-flash-tts:streamGenerateContent?alt=sse');
    expect((init.headers as Record<string, string>)['x-goog-api-key']).toBe('AQ.test-key');
    const sent = JSON.parse(init.body as string);
    expect(sent.contents[0].parts[0].text).toBe('Сейчас посмотрю на позицию.');
    expect(sent.generationConfig.responseModalities).toEqual(['AUDIO']);
  });

  it('refuses without a user, without a key, without text; a quota, no credit and a failure are told apart', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../voice/tts/route');
    expect((await POST(makeRequest({ text: 'x' }))).status).toBe(401);
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    expect((await POST(makeRequest({ text: 'x' }))).status).toBe(500);   // no key at all
    process.env.OPENROUTER_API_KEY = 'sk-or-test';
    expect((await POST(makeRequest({}))).status).toBe(400);
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
